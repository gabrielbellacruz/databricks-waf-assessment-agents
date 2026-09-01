"""Write agent run state and findings directly to Lakebase (Postgres).

Runs inside the Job. Uses **pg8000** - a pure-Python driver - on purpose: a
native libpq (``psycopg2-binary`` / ``psycopg[binary]``) aborts with SIGABRT on
the Databricks serverless runtime, but a pure-Python driver has no native code
to conflict, so it connects fine.

The Job runs as the app's service principal, which owns the app schema (default
``waf``) and has CAN_CONNECT_AND_CREATE on the database, so it can UPDATE the
run row the app created (status=queued) and INSERT findings. Connection
coordinates are passed by the app as job parameters - it knows them from its own
injected env (see backend/server/agents.py) - and the Lakebase password is a
short-lived OAuth token minted per connection via the Databricks SDK.

If no DB coordinates are configured (e.g. a local dry-run), ``ResultsStore.available``
is False and callers fall back to printing findings.
"""

from __future__ import annotations

import contextlib
import json
import ssl
import uuid
from dataclasses import dataclass
from typing import Any

from waf_agents.core.models import Finding


@dataclass(frozen=True)
class DbConfig:
    """Lakebase connection coordinates. ``endpoint_name`` is the Lakebase
    endpoint path used to mint a credential (e.g.
    ``projects/<p>/branches/<b>/endpoints/<e>``)."""

    host: str = ""
    port: int = 5432
    database: str = "waf"
    user: str = ""
    schema: str = "waf"
    endpoint_name: str = ""

    @property
    def available(self) -> bool:
        return bool(self.host and self.database and self.user and self.endpoint_name)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


class ResultsStore:
    """Persists run progress and findings for one agent run to Lakebase.

    A single connection is opened lazily and reused across the run (runs are
    short - minutes - so the ~1h token never expires mid-run). Each write is its
    own autocommit statement; a stale connection is transparently reopened once.
    """

    def __init__(self, cfg: DbConfig, run_id: str, assessment_id: str, layer: str) -> None:
        self._cfg = cfg
        self._run_id = run_id
        self._assessment_id = assessment_id
        self._layer = layer
        self._ws: Any = None  # lazily-created databricks.sdk.WorkspaceClient
        self._conn: Any = None  # lazily-opened pg8000 connection

    @property
    def available(self) -> bool:
        return self._cfg.available

    # -- connection ------------------------------------------------------

    def _token(self) -> str:
        """Mint a fresh short-lived Lakebase OAuth credential for the endpoint,
        via the Job's ambient service-principal auth."""
        if self._ws is None:
            from databricks.sdk import WorkspaceClient

            self._ws = WorkspaceClient()
        resp = self._ws.api_client.do(
            "POST", "/api/2.0/postgres/credentials", body={"endpoint": self._cfg.endpoint_name}
        )
        return resp["token"]

    def _open(self):
        import pg8000.dbapi  # type: ignore[import-untyped]

        # Mirror the app's sslmode=require: encrypt, but don't verify the cert
        # (Lakebase presents a managed cert; the app connects the same way).
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        conn = pg8000.dbapi.connect(
            user=self._cfg.user,
            host=self._cfg.host,
            port=self._cfg.port,
            database=self._cfg.database,
            password=self._token(),
            ssl_context=ctx,
        )
        conn.autocommit = True
        cur = conn.cursor()
        # Pin the session to the app-owned schema so unqualified table names
        # resolve there, never `public` (the SP can't write `public`).
        cur.execute(f'SET search_path TO "{self._cfg.schema}"')
        cur.close()
        return conn

    def _execute(self, sql: str, params: tuple) -> None:
        try:
            conn = self._conn or self._open()
            self._conn = conn
            cur = conn.cursor()
            cur.execute(sql, params)
            cur.close()
        except Exception:
            # Reopen once (e.g. the pooled connection went stale) and retry.
            self._conn = None
            conn = self._open()
            self._conn = conn
            cur = conn.cursor()
            cur.execute(sql, params)
            cur.close()

    def close(self) -> None:
        if self._conn is not None:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None

    # -- writes ----------------------------------------------------------

    def mark_running(self, n_total: int) -> None:
        self._execute(
            "UPDATE agent_runs SET status = 'running', n_total = %s WHERE run_id = %s",
            (n_total, self._run_id),
        )

    def update_progress(self, n_done: int) -> None:
        self._execute(
            "UPDATE agent_runs SET status = CASE WHEN status = 'queued' THEN 'running' "
            "ELSE status END, n_done = %s WHERE run_id = %s",
            (n_done, self._run_id),
        )

    def write_done(self, findings: list[Finding]) -> None:
        for f in findings:
            d = f.to_dict()
            # Idempotent: a re-run of the terminal write can't duplicate or trip
            # the (run_id, question_id) unique constraint.
            self._execute(
                "INSERT INTO agent_findings "
                "(id, run_id, assessment_id, category_id, pillar_id, question_id, "
                " verdict, score, confidence, rationale, sources, auto_assessable) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CAST(%s AS jsonb), %s) "
                "ON CONFLICT (run_id, question_id) DO NOTHING",
                (
                    _new_id("finding"),
                    self._run_id,
                    self._assessment_id,
                    self._layer,
                    d["pillar_id"],
                    d["question_id"],
                    d["verdict"],
                    d["score"],
                    d["confidence"],
                    d["rationale"],
                    json.dumps(d["sources"]),
                    d["auto_assessable"],
                ),
            )
        self._execute(
            "UPDATE agent_runs SET status = 'done', n_done = %s, finished_at = now() "
            "WHERE run_id = %s",
            (len(findings), self._run_id),
        )

    def mark_failed(self, error: str) -> None:
        self._execute(
            "UPDATE agent_runs SET status = 'failed', error = %s, finished_at = now() "
            "WHERE run_id = %s",
            (error[:2000], self._run_id),
        )
