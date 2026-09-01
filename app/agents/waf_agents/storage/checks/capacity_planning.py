"""Storage capacity planning check (LLM-judged).

Answers:
  STO-OE-05  Plan storage capacity and quotas

Signal: weekly storage-SKU usage_quantity from system.billing.usage over
the last 90 days — a discernible upward or stable trend is the minimal
prerequisite for capacity planning. Cloud-account storage quotas are not
exposed to this agent; this limitation is noted explicitly. The LLM judge
decides whether the trend evidence suggests proactive planning vs reactive
behavior.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT date_trunc('week', usage_date) AS week_start,
       SUM(usage_quantity) AS total_storage_dbu
FROM system.billing.usage
WHERE sku_name ILIKE '%STORAGE%'
  AND usage_date >= current_date() - INTERVAL 90 DAYS
GROUP BY week_start
ORDER BY week_start
LIMIT 13\
"""

_NOTE = (
    "Cloud-account storage quotas and hard limits are not visible to this agent "
    "via system tables. system.billing.usage provides the only available signal "
    "for storage growth trajectory; whether formal capacity plans, quota alerts, "
    "or budget thresholds exist cannot be determined from system tables alone "
    "and requires manual confirmation."
)

_REF = "https://docs.databricks.com/en/admin/system-tables/billing.html"


@register(layer="storage", question_ids=["STO-OE-05"])
class CapacityPlanningCheck(Check):
    """Assess storage capacity planning readiness via weekly billing usage trends.

    A 90-day weekly storage trend from billing.usage shows whether growth is
    visible enough to plan against. Cloud quota visibility gaps are noted
    explicitly. The LLM judge weighs trend predictability and notes limitations.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        weeks_with_data = len(rows)
        if weeks_with_data > 0:
            total_qty = sum(float(r.get("total_storage_dbu") or 0) for r in rows)
            summary = (
                f"{weeks_with_data} weeks of storage-SKU billing data found over the "
                f"last 90 days (total_storage_dbu={total_qty:.2f}); "
                "weekly growth trend is observable for capacity planning"
            )
        else:
            summary = (
                "No storage-SKU billing records found in system.billing.usage "
                "for the last 90 days — capacity trend cannot be assessed"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=rows[:13],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
