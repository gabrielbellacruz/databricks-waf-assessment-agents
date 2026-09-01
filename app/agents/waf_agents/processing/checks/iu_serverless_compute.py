"""Serverless compute for transformations check (deterministic).

Answers:
  PRO-IU-03  Use serverless compute for transformations

Signal: the share of recent compute billing DBUs on serverless SKUs,
from ``system.billing.usage``.  Serverless compute eliminates cluster
management overhead and is the recommended approach for transformation
workloads where appropriate.  MEDIUM confidence: the ratio covers
workspace-wide compute spend, not transformation workloads specifically,
and "where appropriate" is a judgement call.
Denominator 0 -> UNKNOWN/LOW.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.50
_PARTIAL_THRESHOLD = 0.15
_WINDOW_DAYS = 30


@register(layer="processing", question_ids=["PRO-IU-03"])
class ProcessingServerlessComputeCheck(Check):
    """Assess serverless compute adoption for transformation workloads.

    Queries ``system.billing.usage`` for the ratio of serverless SKU DBUs
    to total compute DBUs over the last 30 days.  A high ratio indicates
    the team leverages serverless compute, reducing operational overhead.
    Confidence is MEDIUM because the signal is workspace-wide, not
    transformation-specific.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        sql = (
            "SELECT "
            "SUM(usage_quantity) AS total_dbus, "
            "SUM(CASE WHEN sku_name ILIKE '%SERVERLESS%' THEN usage_quantity ELSE 0 END) "
            "AS serverless_dbus "
            "FROM system.billing.usage "
            f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
            "AND sku_name ILIKE '%COMPUTE%'"
        )
        rows = ctx.sql.query(sql)
        row = rows[0] if rows else {"total_dbus": None, "serverless_dbus": None}
        total = float(row.get("total_dbus") or 0)
        serverless = float(row.get("serverless_dbus") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{serverless:.2f} of {total:.2f} compute DBUs "
                    f"(last {_WINDOW_DAYS}d) are on serverless SKUs"
                ),
                detail=sql,
                rows=[{"total_dbus": total, "serverless_dbus": serverless}],
                ref="https://docs.databricks.com/en/compute/serverless/index.html",
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
                    "No compute billing usage in the window; "
                    "cannot assess serverless adoption for transformations."
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
                f"{serverless:.2f} of {total:.2f} compute DBUs ({ratio:.0%}) over the last "
                f"{_WINDOW_DAYS} days are on serverless SKUs; threshold for 'met' is "
                f"{_MET_THRESHOLD:.0%}. "
                "Note: this is a proxy signal — the ratio covers all compute spend, not "
                "transformation workloads specifically, and 'where appropriate' requires "
                "manual judgment on workload fit."
            ),
            sources=evidence,
        )
