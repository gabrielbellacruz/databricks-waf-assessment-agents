"""Serverless compute for orchestrated tasks check (deterministic).

Answers:
  ORC-IU-04  Use serverless for orchestrated tasks where suitable

Signal: share of recent compute spend on serverless SKUs that are
associated with jobs/workflows, from ``system.billing.usage``.
Deterministic ratio vs a threshold -> MEDIUM confidence because
'where suitable' is a judgement call and the SKU filter is a heuristic
rather than a perfect scope boundary.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.50
_PARTIAL_THRESHOLD = 0.15
_WINDOW_DAYS = 30

_SQL = (
    "SELECT "
    "SUM(usage_quantity) AS total_dbus, "
    "SUM(CASE WHEN sku_name ILIKE '%SERVERLESS%' THEN usage_quantity ELSE 0 END) "
    "AS serverless_dbus "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "AND (sku_name ILIKE '%JOB%' OR sku_name ILIKE '%WORKFLOW%' OR sku_name ILIKE '%COMPUTE%')"
)

_REF = "https://docs.databricks.com/en/compute/serverless/index.html"


@register(layer="orchestration", question_ids=["ORC-IU-04"])
class ServerlessOrchestrationCheck(Check):
    """Deterministic check for ORC-IU-04: serverless for orchestrated tasks.

    Measures the share of job/workflow compute DBUs consumed by serverless
    SKUs over the last 30 days.  Confidence is MEDIUM: 'where suitable'
    requires manual judgment on workload fit, and the SKU filter covers all
    compute (not orchestration-exclusively).
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total_dbus": None, "serverless_dbus": None}
        total = float(row.get("total_dbus") or 0)
        serverless = float(row.get("serverless_dbus") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{serverless:.2f} of {total:.2f} job/workflow compute DBUs "
                    f"(last {_WINDOW_DAYS}d) are on serverless SKUs"
                ),
                detail=_SQL,
                rows=[{"total_dbus": total, "serverless_dbus": serverless}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total_dbus"]
        serverless = row["serverless_dbus"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No job/workflow compute billing usage in the window to evaluate "
                    "serverless adoption."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = serverless / total
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
            confidence=Confidence.MEDIUM,
            score=round(ratio, 4),
            rationale=(
                f"{serverless:.2f} of {total:.2f} job/workflow compute DBUs ({ratio:.0%}) "
                f"over the last {_WINDOW_DAYS} days are on serverless SKUs; "
                f"threshold for 'met' is {_MET_THRESHOLD:.0%}. "
                "Confidence is MEDIUM: 'where suitable' requires manual judgment on "
                "workload fit, and this signal covers all compute SKUs matching "
                "JOB/WORKFLOW/COMPUTE rather than orchestration specifically."
            ),
            sources=evidence,
        )
