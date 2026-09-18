"""Token/endpoint cost attribution check (LLM-judged).

Answers:
  AI-CO-04  Track and attribute token/endpoint cost

Signals:
  * system.billing.usage – custom_tags coverage on serving SKUs; tagged records
    are attributable to an app or team.
  * system.ai_gateway.usage – presence of AI Gateway request telemetry is
    evidence that a rate-limiting and attribution layer is configured.

Limitation: rate-limit configurations and per-app spending policies are not
exposed in system tables; a reviewer should confirm whether spend controls are
set up in AI Gateway.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 30

_TAG_SQL = (
    "SELECT COUNT(*) AS total, "
    "SUM(CASE WHEN custom_tags IS NOT NULL AND size(custom_tags) > 0 "
    "THEN 1 ELSE 0 END) AS tagged "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "AND sku_name ILIKE '%SERVING%'"
)

_GATEWAY_SQL = (
    "SELECT COUNT(*) AS request_count, "
    "SUM(input_tokens) AS input_tokens, "
    "SUM(output_tokens) AS output_tokens "
    "FROM system.ai_gateway.usage "
    f"WHERE event_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS"
)

_NOTE = (
    "Rate-limit configurations and per-app spending caps are not exposed in "
    "system tables; a reviewer should verify whether spend controls are configured "
    "in AI Gateway."
)

_REF = "https://docs.databricks.com/en/ai-gateway/index.html"


@register(layer="ai", question_ids=["AI-CO-04"])
class CostAttributionCheck(Check):
    """Assess whether token/endpoint cost is tracked and attributable.

    Collects custom-tag coverage on serving billing SKUs and AI Gateway request
    telemetry.  Tagged billing records and an active Gateway are both proxies for
    cost-attribution discipline; the LLM judge weighs them together.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        tag_rows = ctx.sql.query(_TAG_SQL)
        tag_row = tag_rows[0] if tag_rows else {"total": 0, "tagged": 0}
        total = int(tag_row.get("total") or 0)
        tagged = int(tag_row.get("tagged") or 0)
        tag_pct = round(100.0 * tagged / total, 1) if total > 0 else 0.0

        if total == 0:
            tag_summary = (
                f"No serving billing usage found in the last {_WINDOW_DAYS} days"
            )
        else:
            tag_summary = (
                f"{tagged} of {total} serving billing records carry a custom tag "
                f"({tag_pct}% coverage) in the last {_WINDOW_DAYS} days"
            )

        gw_rows = ctx.sql.query(_GATEWAY_SQL)
        gw_row = gw_rows[0] if gw_rows else {"request_count": 0}
        gw_count = int(gw_row.get("request_count") or 0)
        gw_input = int(gw_row.get("input_tokens") or 0)
        gw_output = int(gw_row.get("output_tokens") or 0)

        if gw_count == 0:
            gw_summary = (
                f"No AI Gateway usage found in the last {_WINDOW_DAYS} days — "
                "AI Gateway may not be configured"
            )
        else:
            gw_summary = (
                f"{gw_count} AI Gateway requests in the last {_WINDOW_DAYS} days; "
                f"input tokens: {gw_input}, output tokens: {gw_output}"
            )

        return [
            Evidence(
                kind="sql",
                summary=tag_summary,
                detail=_TAG_SQL,
                rows=[{"total": total, "tagged": tagged, "tagged_pct": tag_pct}],
                ref=_REF,
            ),
            Evidence(
                kind="sql",
                summary=gw_summary,
                detail=_GATEWAY_SQL,
                rows=[
                    {
                        "request_count": gw_count,
                        "input_tokens": gw_input,
                        "output_tokens": gw_output,
                    }
                ],
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
