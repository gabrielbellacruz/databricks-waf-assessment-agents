"""Storage cost attribution check (LLM-judged).

Answers:
  STO-CO-04  Attribute storage cost by owner

Signal: the share of STORAGE billing usage records (sku_name ILIKE '%STORAGE%') that
carry at least one custom_tag, from system.billing.usage. Custom tags (custom_tags MAP)
make usage attributable to an owner or team. This mirrors the tag-coverage approach in
the ingestion CostTaggingCheck but scopes the query to storage SKUs only. The LLM judge
weighs the tagged / untagged ratio and decides whether storage cost attribution is in
place.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 30

_SQL = (
    "SELECT COUNT(*) AS total, "
    "SUM(CASE WHEN custom_tags IS NOT NULL AND size(custom_tags) > 0 "
    "THEN 1 ELSE 0 END) AS tagged "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "AND sku_name ILIKE '%STORAGE%'"
)

_REF = "https://docs.databricks.com/en/admin/account-settings/usage-detail-tags.html"


@register(layer="storage", question_ids=["STO-CO-04"])
class StorageCostAttributionCheck(Check):
    """Assess whether storage billing is tagged for cost attribution.

    Queries system.billing.usage scoped to STORAGE SKUs and computes the share of
    records that carry at least one custom tag. Tagged records are attributable to a
    team or owner; untagged records are a cost-attribution gap. The LLM judge renders
    a verdict from the coverage ratio.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total": 0, "tagged": 0}
        total = int(row.get("total") or 0)
        tagged = int(row.get("tagged") or 0)
        pct = round(100.0 * tagged / total, 1) if total > 0 else 0.0

        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{tagged} of {total} STORAGE billing usage records "
                    f"(last {_WINDOW_DAYS}d) carry a custom tag ({pct}% tag coverage)"
                ),
                detail=_SQL,
                rows=[{"total": total, "tagged": tagged, "tagged_pct": pct}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
