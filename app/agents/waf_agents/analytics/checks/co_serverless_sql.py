"""Serverless SQL warehouse adoption check (deterministic).

Answers:
  ANA-CO-03  Prefer serverless for spiky analytics demand

Signal: share of recent SQL warehouse DBUs consumed on the SERVERLESS_SQL SKU
vs all SQL SKUs, from ``system.billing.usage``.  Serverless warehouses start
instantly without cluster warm-up, which makes them well-suited to spiky or
unpredictable workloads.  Deterministic ratio vs threshold.  Confidence is
MEDIUM because the ratio covers workspace-wide SQL spend; whether serverless
is appropriate for every workload requires manual judgment.
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
    "SUM(usage_quantity) AS total_sql_dbus, "
    "SUM(CASE WHEN sku_name ILIKE '%SERVERLESS%' THEN usage_quantity ELSE 0 END) "
    "AS serverless_dbus "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "AND sku_name ILIKE '%SQL%'"
)


@register(layer="analytics", question_ids=["ANA-CO-03"])
class ServerlessSqlCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total_sql_dbus": None, "serverless_dbus": None}
        total = float(row.get("total_sql_dbus") or 0)
        serverless = float(row.get("serverless_dbus") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{serverless:.2f} of {total:.2f} SQL warehouse DBUs "
                    f"(last {_WINDOW_DAYS}d) are on the serverless SKU"
                ),
                detail=_SQL,
                rows=[{"total_sql_dbus": total, "serverless_dbus": serverless}],
                ref=(
                    "https://docs.databricks.com/en/compute/sql-warehouse/"
                    "serverless-sql-warehouse.html"
                ),
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total_sql_dbus"]
        serverless = row["serverless_dbus"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No SQL warehouse billing usage in the window to evaluate "
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
                f"{serverless:.2f} of {total:.2f} SQL warehouse DBUs ({ratio:.0%}) over "
                f"the last {_WINDOW_DAYS} days are on the serverless SKU; threshold for "
                f"'met' is {_MET_THRESHOLD:.0%}. "
                "Serverless warehouses start instantly and are recommended for spiky or "
                "unpredictable analytical demand; 'where appropriate' still requires manual "
                "judgment on workload fit."
            ),
            sources=evidence,
        )
