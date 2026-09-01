"""Scale-to-zero endpoint check (LLM-judged).

Answers:
  AI-CO-05  Scale endpoints to zero when idle

Signals:
  * system.serving.endpoint_usage – per-endpoint daily request counts over the
    last 30 days.  Endpoints with many zero-request days are idle and incur
    unnecessary serving cost if scale-to-zero is not configured.
  * system.billing.usage – total serving DBUs in the same window; high billing
    alongside idle endpoint-days is a direct proxy for wasted spend.

Limitation: scale-to-zero configuration is not exposed in system tables.
Idle billing days indicate an opportunity; whether scale-to-zero is already
configured (but not triggering) or simply not set up requires manual confirmation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 30

_IDLE_SQL = (
    "SELECT endpoint_name, "
    "COUNT(*) AS days_active, "
    "SUM(CASE WHEN total_request_count = 0 THEN 1 ELSE 0 END) AS idle_days, "
    "SUM(total_request_count) AS total_requests "
    "FROM system.serving.endpoint_usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "GROUP BY endpoint_name "
    "ORDER BY idle_days DESC "
    "LIMIT 20"
)

_BILLING_SQL = (
    "SELECT SUM(usage_quantity) AS serving_dbu "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "AND sku_name ILIKE '%SERVING%'"
)

_NOTE = (
    "Scale-to-zero configuration is not exposed in system tables. Endpoints with "
    "many idle days and non-zero billing indicate a cost-optimisation opportunity, "
    "but whether scale-to-zero is already configured or simply not set up requires "
    "manual confirmation."
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/scale-to-zero.html"


@register(layer="ai", question_ids=["AI-CO-05"])
class ScaleToZeroCheck(Check):
    """Assess whether intermittent endpoints scale to zero when idle.

    Collects per-endpoint idle-day counts from system.serving.endpoint_usage and
    total serving billing from system.billing.usage.  Endpoints with significant
    idle days alongside active billing are strong candidates for scale-to-zero.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        idle_rows = ctx.sql.query(_IDLE_SQL)
        billing_rows = ctx.sql.query(_BILLING_SQL)

        if idle_rows:
            total_endpoints = len(idle_rows)
            endpoints_with_idle = sum(
                1 for r in idle_rows if int(r.get("idle_days") or 0) > 0
            )
            total_idle_days = sum(int(r.get("idle_days") or 0) for r in idle_rows)
            idle_summary = (
                f"{total_endpoints} endpoints tracked in the last {_WINDOW_DAYS} days; "
                f"{endpoints_with_idle} have at least one idle day; "
                f"total idle endpoint-days: {total_idle_days}"
            )
        else:
            idle_summary = (
                f"No serving endpoint usage found in the last {_WINDOW_DAYS} days"
            )

        billing_row = billing_rows[0] if billing_rows else {"serving_dbu": 0}
        serving_dbu = float(billing_row.get("serving_dbu") or 0)
        billing_summary = (
            f"Total serving billing: {serving_dbu:.1f} DBU "
            f"in the last {_WINDOW_DAYS} days"
        )

        return [
            Evidence(
                kind="sql",
                summary=idle_summary,
                detail=_IDLE_SQL,
                rows=idle_rows[:20],
                ref=_REF,
            ),
            Evidence(
                kind="sql",
                summary=billing_summary,
                detail=_BILLING_SQL,
                rows=[{"serving_dbu": serving_dbu}],
                ref=_REF,
            ),
            Evidence(
                kind="note",
                summary=_NOTE,
                ref=_REF,
            ),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
