"""Storage growth monitoring check (LLM-judged).

Answers:
  STO-OE-02  Monitor storage growth and table health

Signal: daily storage-SKU usage_quantity from system.billing.usage over
the last 60 days shows whether storage growth is observable and trackable.
Per-table file-count and health metrics are not available in system tables
— this gap is noted explicitly. The LLM judge weighs trend visibility
against the inability to observe per-table health directly.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT usage_date, SUM(usage_quantity) AS total_storage_dbu
FROM system.billing.usage
WHERE sku_name ILIKE '%STORAGE%'
  AND usage_date >= current_date() - INTERVAL 60 DAYS
GROUP BY usage_date
ORDER BY usage_date
LIMIT 60\
"""

_NOTE = (
    "Per-table file-count, fragment count, and table health metrics are not "
    "exposed in the system tables available to this agent. "
    "system.billing.usage shows aggregate storage consumption as a proxy for "
    "growth visibility, but cannot confirm whether table-level health "
    "(e.g. excessive small files, stale data) is being actively monitored. "
    "A dedicated observability dashboard or manual confirmation is needed to "
    "verify table-health monitoring."
)

_REF = "https://docs.databricks.com/en/admin/system-tables/billing.html"


@register(layer="storage", question_ids=["STO-OE-02"])
class StorageMonitoringCheck(Check):
    """Assess storage-growth monitoring using billing.usage storage SKU trends.

    Daily storage-quantity over 60 days shows whether growth can be tracked.
    Per-table health metrics are not visible in system tables — a note
    evidence records the gap. The LLM judge evaluates both the trend signal
    and the noted limitation.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        days_with_data = len(rows)
        if days_with_data > 0:
            total_qty = sum(float(r.get("total_storage_dbu") or 0) for r in rows)
            summary = (
                f"{days_with_data} days of storage-SKU billing data found over the "
                f"last 60 days (total_storage_dbu={total_qty:.2f}); "
                "trend is observable from system.billing.usage"
            )
        else:
            summary = (
                "No storage-SKU billing records found in system.billing.usage "
                "for the last 60 days — storage growth cannot be assessed from this signal"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=rows[:25],
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
