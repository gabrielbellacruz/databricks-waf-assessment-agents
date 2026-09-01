"""Workflow ownership check (deterministic).

Answers:
  ORC-DG-01  Assign clear ownership to every workflow

Signal: the share of active jobs whose ``run_as`` field is set (non-null,
non-empty), from ``system.lakeflow.jobs``.  A job without ``run_as`` runs as
the creating user's personal identity, which makes ownership ambiguous for
access audits and off-boarding.

Deterministic ratio vs a threshold -> HIGH confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.90
_PARTIAL_THRESHOLD = 0.60

_SQL = (
    "SELECT COUNT(*) AS total_jobs, "
    "SUM(CASE WHEN run_as IS NOT NULL AND run_as <> '' THEN 1 ELSE 0 END) "
    "AS owned_jobs "
    "FROM system.lakeflow.jobs "
    "WHERE delete_time IS NULL"
)

_REF = "https://docs.databricks.com/en/workflows/jobs/jobs-2.0-api.html"


@register(layer="orchestration", question_ids=["ORC-DG-01"])
class WorkflowOwnershipCheck(Check):
    """Deterministic check for ORC-DG-01: clear ownership on every workflow.

    A job is counted as 'owned' when its ``run_as`` field is populated.
    Jobs with no ``run_as`` run as the creator's personal account, which
    provides no stable ownership signal after the creator leaves.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total_jobs": 0, "owned_jobs": 0}
        total = int(row.get("total_jobs") or 0)
        owned = int(row.get("owned_jobs") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{owned} of {total} active jobs have an explicit run_as owner set"
                ),
                detail=_SQL,
                rows=[{"total_jobs": total, "owned_jobs": owned}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total_jobs"]
        owned = row["owned_jobs"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No active jobs found in system.lakeflow.jobs to evaluate ownership."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = owned / total
        if ratio >= _MET_THRESHOLD:
            verdict = Verdict.MET
        elif ratio >= _PARTIAL_THRESHOLD:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.NOT_MET

        return Finding(
            question_id=question.id,
            pillar_id=question.pillar_id,
            verdict=verdict,
            confidence=Confidence.HIGH,
            score=round(ratio, 4),
            rationale=(
                f"{owned} of {total} active jobs ({ratio:.0%}) have an explicit run_as "
                f"identity set; threshold for 'met' is {_MET_THRESHOLD:.0%}. "
                "Jobs without run_as run as the creator's personal account, making "
                "ownership unclear for audits and off-boarding workflows."
            ),
            sources=evidence,
        )
