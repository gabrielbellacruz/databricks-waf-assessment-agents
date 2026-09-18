"""SQL warehouse health and query-failure monitoring check (LLM-judged).

Answers:
  ANA-OE-02  Monitor SQL warehouse health and query failures

Alert and notification configuration for SQL warehouses is not exposed in
system tables. The observable proxies are the query failure rate from
system.query.history (last 30 days) and warehouse scaling events from
system.compute.warehouse_events. A workspace where monitoring is absent tends
to accumulate unnoticed failures. The LLM judge weighs both signals plus a
note about the observability gap.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_QUERY_HISTORY_SQL = """\
SELECT COUNT(*) AS total_queries,
       SUM(CASE WHEN execution_status = 'FAILED' THEN 1 ELSE 0 END) AS failed_queries
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_WAREHOUSE_EVENTS_SQL = """\
SELECT COUNT(*) AS event_count,
       COUNT(DISTINCT warehouse_id) AS warehouse_count
FROM system.compute.warehouse_events
WHERE event_time >= current_timestamp() - INTERVAL 7 DAYS\
"""

_MONITOR_NOTE = (
    "Warehouse alert/notification configuration (email/webhook on failure or queue spike) "
    "is not exposed in system tables and cannot be observed via this agent. "
    "The query failure rate and warehouse events are proxies for monitoring health; "
    "whether alerts are wired requires manual confirmation."
)

_REF = "https://docs.databricks.com/en/sql/admin/alert-on-queries.html"


@register(layer="analytics", question_ids=["ANA-OE-02"])
class WarehouseMonitoringCheck(Check):
    """Assess warehouse monitoring health via query failure rate and event volume.

    Evidence is gathered from system.query.history (last 30 days) and
    system.compute.warehouse_events (last 7 days). A note evidence records
    that alert configuration is not visible to the agent.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        qh_rows = ctx.sql.query(_QUERY_HISTORY_SQL)
        if qh_rows:
            total = int(qh_rows[0].get("total_queries") or 0)
            failed = int(qh_rows[0].get("failed_queries") or 0)
        else:
            total = 0
            failed = 0

        if total > 0:
            failure_pct = round(100.0 * failed / total, 1)
            qh_summary = (
                f"{failed} of {total} queries failed in the last 30 days "
                f"({failure_pct}%)"
            )
        else:
            failure_pct = 0.0
            qh_summary = (
                "No queries found in system.query.history for the last 30 days"
            )

        we_rows = ctx.sql.query(_WAREHOUSE_EVENTS_SQL)
        if we_rows:
            event_count = int(we_rows[0].get("event_count") or 0)
            wh_count = int(we_rows[0].get("warehouse_count") or 0)
        else:
            event_count = 0
            wh_count = 0

        we_summary = (
            f"{event_count} warehouse events recorded across {wh_count} warehouse(s) "
            f"in the last 7 days"
        )

        return [
            Evidence(
                kind="sql",
                summary=qh_summary,
                detail=_QUERY_HISTORY_SQL,
                rows=[
                    {
                        "total_queries": total,
                        "failed_queries": failed,
                        "failure_pct": failure_pct,
                    }
                ],
                ref="https://docs.databricks.com/en/monitoring/system-tables/query-history.html",
            ),
            Evidence(
                kind="sql",
                summary=we_summary,
                detail=_WAREHOUSE_EVENTS_SQL,
                rows=[{"event_count": event_count, "warehouse_count": wh_count}],
                ref="https://docs.databricks.com/en/monitoring/system-tables/compute.html",
            ),
            Evidence(
                kind="note",
                summary=_MONITOR_NOTE,
                rows=[],
                ref=_REF,
            ),
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
