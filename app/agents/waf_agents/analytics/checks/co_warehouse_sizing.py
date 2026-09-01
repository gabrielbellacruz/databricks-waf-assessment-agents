"""Warehouse sizing check (LLM-judged).

Answers:
  ANA-CO-01  Use SQL warehouses sized to analytics workloads

Signal:
  - Warehouse cluster_size distribution from system.compute.warehouses
    (cluster_size, warehouse_type, min/max clusters, count per configuration).
  - Query-load stats from system.query.history (SELECT count, avg/max duration,
    slow queries) as a proxy for demand intensity over the last 30 days.
  - A note that "correctly sized" is a judgment call requiring manual review.

Whether a warehouse is appropriately sized depends on workload patterns: an
undersized warehouse produces long queues, an oversized one wastes cost.
Autoscaling (min < max clusters) helps buffer variable demand. The LLM weighs
the observed size distribution against query-load evidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WAREHOUSE_SQL = (
    "SELECT cluster_size, warehouse_type, "
    "min_num_clusters, max_num_clusters, COUNT(*) AS cnt "
    "FROM system.compute.warehouses "
    "WHERE state != 'DELETED' "
    "GROUP BY cluster_size, warehouse_type, min_num_clusters, max_num_clusters "
    "ORDER BY cnt DESC "
    "LIMIT 20"
)

_QUERY_LOAD_SQL = (
    "SELECT COUNT(*) AS query_count, "
    "AVG(total_duration_ms) AS avg_duration_ms, "
    "MAX(total_duration_ms) AS max_duration_ms, "
    "SUM(CASE WHEN total_duration_ms > 30000 THEN 1 ELSE 0 END) AS slow_query_count "
    "FROM system.query.history "
    "WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS "
    "AND statement_type = 'SELECT'"
)

_NOTE = (
    "Warehouse sizing appropriateness depends on workload: a warehouse that is too "
    "small produces long query queues, while an oversized one wastes cost. "
    "Autoscaling (min_num_clusters < max_num_clusters) helps absorb variable demand "
    "without permanent over-provisioning. Manual review is recommended to validate sizing "
    "against specific analytical workload patterns."
)


@register(layer="analytics", question_ids=["ANA-CO-01"])
class WarehouseSizingCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        wh_rows = ctx.sql.query(_WAREHOUSE_SQL)

        wh_evidence = Evidence(
            kind="sql",
            summary=(
                f"{sum(int(r.get('cnt') or 1) for r in wh_rows)} active warehouses across "
                f"{len(wh_rows)} size/type configurations"
                if wh_rows
                else "No active warehouses found in system.compute.warehouses"
            ),
            detail=_WAREHOUSE_SQL,
            rows=[{k: v for k, v in r.items()} for r in wh_rows[:20]],
            ref="https://docs.databricks.com/en/compute/sql-warehouse/create-sql-warehouse.html",
        )

        qload_rows = ctx.sql.query(_QUERY_LOAD_SQL)

        if qload_rows:
            row = qload_rows[0]
            qcount = int(row.get("query_count") or 0)
            avg_ms_raw = row.get("avg_duration_ms")
            max_ms_raw = row.get("max_duration_ms")
            slow = int(row.get("slow_query_count") or 0)
            avg_ms = round(float(avg_ms_raw), 1) if avg_ms_raw is not None else None
            max_ms = round(float(max_ms_raw)) if max_ms_raw is not None else None
            if qcount > 0:
                load_summary = (
                    f"{qcount} SELECT queries in last 30 days; "
                    f"avg {avg_ms}ms, max {max_ms}ms; "
                    f"{slow} slow (>30s)"
                )
            else:
                load_summary = (
                    "No SELECT queries found in system.query.history for last 30 days"
                )
        else:
            qcount = 0
            load_summary = "No query history available from system.query.history"

        load_evidence = Evidence(
            kind="sql",
            summary=load_summary,
            detail=_QUERY_LOAD_SQL,
            rows=qload_rows[:1],
            ref="https://docs.databricks.com/en/sql/admin/query-history.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
        )

        return [wh_evidence, load_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
