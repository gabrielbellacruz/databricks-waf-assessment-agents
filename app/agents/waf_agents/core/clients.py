"""Execution clients and the context checks receive.

A check never talks to Databricks directly; it goes through ``AgentContext``.
That keeps checks pure and unit-testable: tests inject ``FakeSqlClient`` with
recorded rows, so the whole graph runs offline with no workspace.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from waf_agents.core.models import Scope

# An uploaded document image, sent to the LLM judge as a vision block.
DocImage = tuple[str, bytes]  # (mime type, raw bytes)


@runtime_checkable
class SqlClient(Protocol):
    """Runs read-only SQL (system tables, information_schema) and returns rows
    as dicts."""

    def query(self, sql: str) -> list[dict]: ...


class FakeSqlClient:
    """Test double. Maps a substring of the SQL to canned rows so a test can
    say 'when a query mentions data_source_format, return these rows'."""

    def __init__(self, responses: dict[str, list[dict]] | None = None):
        self._responses = responses or {}
        self.calls: list[str] = []

    def query(self, sql: str) -> list[dict]:
        self.calls.append(sql)
        for needle, rows in self._responses.items():
            if needle in sql:
                return rows
        return []


@runtime_checkable
class ArtifactClient(Protocol):
    """Reads workspace *configuration* artifacts (not data) over the Databricks
    REST API: job / pipeline / cluster definitions, external locations, and
    secret-scope names. LLM-judged checks use these for signals the system
    tables don't expose (git source, notification settings, autotermination,
    continuous-vs-triggered, etc.). Every method returns plain JSON-able data."""

    def jobs(self) -> list[dict]: ...
    def pipelines(self) -> list[dict]: ...
    def clusters(self) -> list[dict]: ...
    def external_locations(self) -> list[dict]: ...
    def secret_scopes(self) -> list[str]: ...


class FakeArtifactClient:
    """Test double: returns exactly the artifact lists it was constructed with."""

    def __init__(
        self,
        *,
        jobs: list[dict] | None = None,
        pipelines: list[dict] | None = None,
        clusters: list[dict] | None = None,
        external_locations: list[dict] | None = None,
        secret_scopes: list[str] | None = None,
    ) -> None:
        self._jobs = jobs or []
        self._pipelines = pipelines or []
        self._clusters = clusters or []
        self._external_locations = external_locations or []
        self._secret_scopes = secret_scopes or []

    def jobs(self) -> list[dict]:
        return self._jobs

    def pipelines(self) -> list[dict]:
        return self._pipelines

    def clusters(self) -> list[dict]:
        return self._clusters

    def external_locations(self) -> list[dict]:
        return self._external_locations

    def secret_scopes(self) -> list[str]:
        return self._secret_scopes


@runtime_checkable
class LlmClient(Protocol):
    """Chat completion against a Databricks serving endpoint. Returns the raw
    assistant text; WAF-specific prompting and parsing live in ``core.llm``.

    ``images`` (optional) are uploaded architecture diagrams sent as vision
    blocks alongside the text prompt - see ``core.context``."""

    def complete(
        self, system: str, user: str, images: list[DocImage] | None = None
    ) -> str: ...


class FakeLlmClient:
    """Test double: returns a canned assistant string and records prompts (and
    any images it was asked to send)."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []
        self.image_calls: list[list[DocImage]] = []

    def complete(
        self, system: str, user: str, images: list[DocImage] | None = None
    ) -> str:
        self.calls.append((system, user))
        self.image_calls.append(list(images or []))
        return self.response


class DatabricksSqlClient:
    """Real client: runs SQL against a warehouse via the Statement Execution
    API (databricks-sdk). Instantiated only inside the Job, where the SDK and
    workspace auth are available."""

    def __init__(self, warehouse_id: str, profile: str | None = None):
        self._warehouse_id = warehouse_id
        self._profile = profile
        self._ws = None

    def _client(self):
        if self._ws is None:
            from databricks.sdk import WorkspaceClient  # lazy: only needed live

            self._ws = (
                WorkspaceClient(profile=self._profile) if self._profile else WorkspaceClient()
            )
        return self._ws

    def _resolve_warehouse(self) -> str:
        """Use the configured warehouse, else pick one from the workspace so the
        Job needs no warehouse config. Prefer a running warehouse, then any."""
        if self._warehouse_id:
            return self._warehouse_id
        from databricks.sdk.service.sql import State

        warehouses = list(self._client().warehouses.list())
        if not warehouses:
            raise RuntimeError("no SQL warehouse available to run agent queries")
        running = next((w for w in warehouses if w.state == State.RUNNING), None)
        self._warehouse_id = (running or warehouses[0]).id  # type: ignore[assignment]
        return self._warehouse_id

    # Some system-table scans (e.g. ILIKE over system.query.history) don't finish
    # within a single execute_statement wait window, which returns PENDING/RUNNING
    # rather than an error. Poll until the statement reaches a terminal state, up
    # to this overall deadline, before giving up.
    _POLL_DEADLINE_S = 240
    _POLL_INTERVAL_S = 5

    def query(self, sql: str) -> list[dict]:
        import time

        from databricks.sdk.service.sql import StatementState

        se = self._client().statement_execution
        resp = se.execute_statement(
            warehouse_id=self._resolve_warehouse(),
            statement=sql,
            wait_timeout="50s",
        )

        # execute_statement caps wait_timeout at 50s; if the statement is still
        # PENDING/RUNNING, poll it to completion rather than treating it as failed.
        deadline = time.monotonic() + self._POLL_DEADLINE_S
        while resp.status and resp.status.state in (
            StatementState.PENDING,
            StatementState.RUNNING,
        ):
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"statement did not finish within {self._POLL_DEADLINE_S}s "
                    f"(last state {resp.status.state})"
                )
            time.sleep(self._POLL_INTERVAL_S)
            resp = se.get_statement(resp.statement_id)  # type: ignore[arg-type]

        if resp.status and resp.status.state != StatementState.SUCCEEDED:
            raise RuntimeError(f"statement failed: {resp.status.state}: {resp.status.error}")
        result = resp.result
        if result is None or result.data_array is None:
            return []
        cols = [c.name for c in resp.manifest.schema.columns]  # type: ignore[union-attr]
        return [dict(zip(cols, row, strict=False)) for row in result.data_array]


class DatabricksArtifactClient:
    """Real ``ArtifactClient`` over databricks-sdk, used inside the Job.

    Best-effort per accessor: an API or permission error yields an empty list,
    so a check whose one signal is missing degrades to 'no evidence' rather than
    crashing the run. Result sizes are capped so a huge estate can't blow up the
    LLM prompt or the API budget."""

    _MAX = 200

    def __init__(self, profile: str | None = None):
        self._profile = profile
        self._ws = None

    def _client(self):
        if self._ws is None:
            from databricks.sdk import WorkspaceClient  # lazy: only needed live

            self._ws = (
                WorkspaceClient(profile=self._profile) if self._profile else WorkspaceClient()
            )
        return self._ws

    def _list(self, fn) -> list[dict]:
        from itertools import islice

        try:
            return [obj.as_dict() for obj in islice(fn(), self._MAX)]
        except Exception:
            return []

    def jobs(self) -> list[dict]:
        return self._list(lambda: self._client().jobs.list(expand_tasks=True))

    def pipelines(self) -> list[dict]:
        # list_pipelines returns state only; fetch each spec (capped) for config.
        from itertools import islice

        try:
            ws = self._client()
            out: list[dict] = []
            for p in islice(ws.pipelines.list_pipelines(), self._MAX):
                try:
                    out.append(ws.pipelines.get(p.pipeline_id).as_dict())
                except Exception:
                    out.append({"pipeline_id": p.pipeline_id, "name": getattr(p, "name", None)})
            return out
        except Exception:
            return []

    def clusters(self) -> list[dict]:
        return self._list(lambda: self._client().clusters.list())

    def external_locations(self) -> list[dict]:
        return self._list(lambda: self._client().external_locations.list())

    def secret_scopes(self) -> list[str]:
        try:
            return [s.name for s in self._client().secrets.list_scopes() if s.name]
        except Exception:
            return []


class ServingEndpointLlm:
    """Real ``LlmClient``: queries a Databricks serving endpoint via databricks-sdk.
    Instantiated only inside the Job.

    We deliberately omit ``temperature``: some reasoning models (e.g. Claude on
    Databricks) reject it with BAD_REQUEST. Repeatability instead comes from a
    strict, evidence-only prompt (see ``core.llm``)."""

    def __init__(self, model: str, profile: str | None = None, max_tokens: int = 1024):
        self._model = model
        self._profile = profile
        self._max_tokens = max_tokens
        self._ws = None

    def _client(self):
        if self._ws is None:
            from databricks.sdk import WorkspaceClient

            self._ws = (
                WorkspaceClient(profile=self._profile) if self._profile else WorkspaceClient()
            )
        return self._ws

    def complete(
        self, system: str, user: str, images: list[DocImage] | None = None
    ) -> str:
        if images:
            return self._complete_multimodal(system, user, images)

        from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

        resp = self._client().serving_endpoints.query(
            name=self._model,
            messages=[
                ChatMessage(role=ChatMessageRole.SYSTEM, content=system),
                ChatMessage(role=ChatMessageRole.USER, content=user),
            ],
            max_tokens=self._max_tokens,
        )
        choices = resp.choices or []
        if not choices or choices[0].message is None:
            return ""
        return choices[0].message.content or ""

    def _complete_multimodal(
        self, system: str, user: str, images: list[DocImage]
    ) -> str:
        """Send text + images as an OpenAI-style multimodal message.

        The typed SDK ``query`` takes only string content, so multimodal goes
        through the raw invocations endpoint (same ``api_client.do`` pattern the
        results store uses for Lakebase credentials). Claude-on-Databricks
        accepts ``image_url`` parts with base64 data URLs."""
        content: list[dict] = [{"type": "text", "text": user}]
        for mime, raw in images:
            b64 = base64.b64encode(raw).decode("ascii")
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
            )
        body = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            "max_tokens": self._max_tokens,
        }
        resp = self._client().api_client.do(
            "POST", f"/serving-endpoints/{self._model}/invocations", body=body
        )
        choices = (resp or {}).get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("message") or {}).get("content") or ""


@dataclass
class ArchitectureContext:
    """User-uploaded architecture documentation for the assessment, gathered once
    per run (see ``core.context``) and shared by every LLM-judged check.

    ``text`` is the concatenated, size-capped text extracted from pdf/txt/md/docx
    uploads; ``images`` are diagram files sent to the model as vision blocks.
    ``doc_names`` are the filenames whose text is included (in order), and
    ``image_names`` the filenames parallel to ``images`` - both let the judge and
    the findings reference a specific source document so a reviewer can find it.
    Falsy when nothing was uploaded (or storage is unavailable), so checks behave
    exactly as before."""

    text: str = ""
    images: list[DocImage] = field(default_factory=list)
    doc_names: list[str] = field(default_factory=list)
    image_names: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.text or self.images)

    def summary(self) -> str:
        """One-line description for logs: what was fed to the judge this run."""
        parts: list[str] = []
        if self.doc_names:
            parts.append(
                f"{len(self.doc_names)} document(s) [{', '.join(self.doc_names)}] "
                f"= {len(self.text):,} chars"
            )
        if self.image_names:
            parts.append(f"{len(self.image_names)} image(s) [{', '.join(self.image_names)}]")
        return "; ".join(parts) if parts else "empty"


@dataclass
class AgentContext:
    """Everything a check needs to run.

    ``sql`` is always present (deterministic checks). ``artifacts`` and ``llm``
    are optional and only used by LLM-judged checks; they're None locally/offline
    so those checks degrade to an ``unassessed`` finding rather than failing.
    ``architecture`` carries uploaded docs (None when there are none or storage
    is unavailable), fed to the LLM judge as extra evidence."""

    assessment_id: str
    layer: str
    sql: SqlClient
    catalogs: list[str] = field(default_factory=list)
    scope: Scope | None = None
    artifacts: ArtifactClient | None = None
    llm: LlmClient | None = None
    architecture: ArchitectureContext | None = None
