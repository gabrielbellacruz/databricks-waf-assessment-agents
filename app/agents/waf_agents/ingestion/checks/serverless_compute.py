"""Serverless compute usage check (deterministic).

Answers:
  ING-PE-04  Use serverless compute for ingestion where appropriate

Signal: share of recent compute spend on serverless SKUs, from
``system.billing.usage``. Deterministic ratio vs a threshold -> MEDIUM confidence
because "where appropriate" is a judgement call and the signal is workspace-wide
(not ingestion-specific).
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.50
_PARTIAL_THRESHOLD = 0.15
_WINDOW_DAYS = 30


@register(layer="ingestion", question_ids=["ING-PE-04"])
class ServerlessComputeCheck(Check):
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
                rationale="No compute billing usage in the window to evaluate serverless adoption.",
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
                "ingestion-specifically, and 'where appropriate' requires manual judgment on "
                "workload fit."
            ),
            sources=evidence,
        )
