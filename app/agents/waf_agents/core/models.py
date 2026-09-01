"""Domain models shared across every layer agent.

Kept dependency-light (stdlib dataclasses/enums) so checks and tests never pull
in LangGraph or Databricks clients just to describe a result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class Verdict(StrEnum):
    """Compliance judgment for one question. Distinct from the frontend's
    workflow ``status`` - see the data-model note in the plan (blocker B1)."""

    MET = "met"
    PARTIAL = "partial"
    NOT_MET = "not_met"
    UNKNOWN = "unknown"  # no signal / no check yet -> defer to a reviewer


class Confidence(StrEnum):
    HIGH = "high"       # deterministic fact from a reliable signal
    MEDIUM = "medium"   # strong proxy / required reasoning
    LOW = "low"         # weak proxy; a reviewer should verify
    NONE = "none"       # not automatically assessable


@dataclass(frozen=True)
class Evidence:
    """One piece of support for a finding, stored for explainability.

    ``detail`` holds a SQL string or an API reference; ``summary`` is a short
    human-readable line; ``rows`` is a *bounded, non-sensitive* sample (counts,
    names) - never raw customer data. Findings are shared org-wide.
    """

    kind: str  # "sql" | "uc_metadata" | "job_config" | "pipeline" | "source_code"
    summary: str
    detail: str = ""
    rows: list[dict] = field(default_factory=list)
    ref: str | None = None  # e.g. a docs URL or object path

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "detail": self.detail,
            "rows": self.rows,
            "ref": self.ref,
        }


@dataclass
class Finding:
    """The agent's answer for one question."""

    question_id: str
    pillar_id: str
    verdict: Verdict
    confidence: Confidence
    rationale: str
    sources: list[Evidence] = field(default_factory=list)
    score: float | None = None  # 0..1 where a ratio is meaningful, else None
    auto_assessable: bool = True

    def to_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "pillar_id": self.pillar_id,
            "verdict": self.verdict.value,
            "confidence": self.confidence.value,
            "rationale": self.rationale,
            "sources": [e.to_dict() for e in self.sources],
            "score": self.score,
            "auto_assessable": self.auto_assessable,
        }

    @classmethod
    def unassessed(cls, question_id: str, pillar_id: str) -> Finding:
        """Result for a question that has no registered check yet. Emitted so a
        newly-added question never breaks a run - it just awaits a reviewer (or a
        future check)."""
        return cls(
            question_id=question_id,
            pillar_id=pillar_id,
            verdict=Verdict.UNKNOWN,
            confidence=Confidence.NONE,
            rationale="No automated check exists for this question yet - requires review.",
            auto_assessable=False,
        )


@dataclass(frozen=True)
class Question:
    """A single WAF question, as loaded from the canonical question set."""

    id: str
    pillar_id: str
    title: str
    principle: str
    details: str | None = None
    checklist: list[str] = field(default_factory=list)


@dataclass
class Scope:
    """The layer-specific inventory a check runs against (e.g. for ingestion:
    entry-point tables and ingestion pipelines/jobs). Built by the agent's
    ``discover_scope`` node so checks are scoped to the layer rather than to
    workspace-global metrics."""

    catalogs: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)  # fully-qualified names
    pipelines: list[str] = field(default_factory=list)
    jobs: list[str] = field(default_factory=list)
    extras: dict = field(default_factory=dict)


def utcnow() -> datetime:
    return datetime.now(UTC)
