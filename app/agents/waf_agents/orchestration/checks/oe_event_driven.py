"""Automated / event-driven triggering check (deterministic).

Answers:
  ORC-OE-01  Use automated, event-driven triggering

Signal: share of current jobs that have a schedule configured (non-null
``schedule`` column) in ``system.lakeflow.jobs``. A job with no schedule can
only be triggered manually; the ratio of scheduled-to-total jobs is a proxy
for how broadly automated triggering is adopted across the workspace.

Note: file-arrival and continuous/streaming triggers also automate execution
but may not populate the ``schedule`` column, so this ratio is a *lower bound*
on automation coverage. Confidence is HIGH (deterministic count).
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.80
_PARTIAL_THRESHOLD = 0.40

_SQL = (
    "SELECT COUNT(*) AS total, "
    "SUM(CASE WHEN schedule IS NOT NULL THEN 1 ELSE 0 END) AS scheduled_jobs "
    "FROM system.lakeflow.jobs "
    "WHERE delete_time IS NULL"
)


@register(layer="orchestration", question_ids=["ORC-OE-01"])
class EventDrivenTriggeringCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total": 0, "scheduled_jobs": 0}
        total = int(row.get("total") or 0)
        scheduled = int(row.get("scheduled_jobs") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{scheduled} of {total} current jobs have an automated trigger "
                    "(schedule configured)"
                ),
                detail=_SQL,
                rows=[{"total": total, "scheduled_jobs": scheduled}],
                ref="https://docs.databricks.com/en/workflows/jobs/schedule.html",
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total"]
        scheduled = row["scheduled_jobs"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No jobs found in system.lakeflow.jobs to evaluate triggering configuration."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = scheduled / total
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
                f"{scheduled} of {total} current jobs ({ratio:.0%}) have a schedule configured, "
                f"indicating automated triggering; threshold for 'met' is {_MET_THRESHOLD:.0%}. "
                "Jobs without a schedule can only be triggered manually. "
                "Note: file-arrival and continuous triggers may not populate this column, "
                "so the actual automation rate may be higher than reported."
            ),
            sources=evidence,
        )
