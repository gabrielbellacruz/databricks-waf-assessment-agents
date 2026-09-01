"""BI connectivity via standard interfaces check (LLM-judged).

Answers:
  ANA-IU-01  Connect BI tools via standard interfaces

Signals:
  * ``system.compute.warehouses`` — count of SQL warehouses (total and running).
    SQL warehouses expose JDBC, ODBC, and the Databricks SQL REST API, which are
    the standard interfaces for connecting external BI tools (Tableau, Power BI,
    Looker, etc.).
  * ``system.query.history`` — recent query volume and distinct user count over
    the past 7 days.  Non-trivial warehouse activity is the primary indicator that
    BI tools are connected and in use.

The LLM judge weighs whether SQL warehouses exist and show recent activity
consistent with BI-tool workloads.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WAREHOUSE_SQL = (
    "SELECT COUNT(*) AS total_warehouses,"
    " SUM(CASE WHEN state = 'RUNNING' THEN 1 ELSE 0 END) AS running_warehouses"
    " FROM system.compute.warehouses"
)

_QUERY_ACTIVITY_SQL = (
    "SELECT COUNT(*) AS recent_queries,"
    " COUNT(DISTINCT user_id) AS distinct_users"
    " FROM system.query.history"
    " WHERE start_time > current_timestamp() - INTERVAL 7 DAYS"
)

_REF = "https://docs.databricks.com/en/compute/sql-warehouse/index.html"


@register(layer="analytics", question_ids=["ANA-IU-01"])
class BiConnectivityCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        wh_rows = ctx.sql.query(_WAREHOUSE_SQL)
        qh_rows = ctx.sql.query(_QUERY_ACTIVITY_SQL)

        wrow = wh_rows[0] if wh_rows else {}
        total_warehouses = int(wrow.get("total_warehouses") or 0)
        running_warehouses = int(wrow.get("running_warehouses") or 0)

        qrow = qh_rows[0] if qh_rows else {}
        recent_queries = int(qrow.get("recent_queries") or 0)
        distinct_users = int(qrow.get("distinct_users") or 0)

        warehouse_evidence = Evidence(
            kind="sql",
            summary=(
                f"{total_warehouses} SQL warehouse(s) found ({running_warehouses} currently"
                " running); SQL warehouses provide JDBC/ODBC/REST interfaces for BI tools"
            ),
            detail=_WAREHOUSE_SQL,
            rows=wh_rows[:10],
            ref=_REF,
        )
        activity_evidence = Evidence(
            kind="sql",
            summary=(
                f"{recent_queries} queries executed by {distinct_users} distinct user(s)"
                " via warehouses in the last 7 days"
            ),
            detail=_QUERY_ACTIVITY_SQL,
            rows=qh_rows[:5],
            ref=_REF,
        )
        return [warehouse_evidence, activity_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
