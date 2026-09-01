"""Production-grade SQL warehouse serving check (LLM-judged).

Answers:
  ANA-R-02  Use managed, production-grade serving for analytics

What constitutes "production-grade" SQL warehouse serving involves several
configuration dimensions that are only partially observable from system tables:
channel stability (CHANNEL_NAME_CURRENT vs CHANNEL_NAME_PREVIEW), warehouse
type (SERVERLESS > PRO > CLASSIC for managed reliability), auto-stop settings
(very short auto_stop_mins on a production warehouse indicates poor reliability
posture), and whether warehouses are dedicated to production workloads.

Observable proxies:
  - ``system.compute.warehouses``: channel_name, warehouse_type, auto_stop_mins,
    min/max_num_clusters — aggregated counts across the warehouse fleet.
  - ``system.compute.warehouse_events``: recent stopping/started events to assess
    availability patterns.

The LLM judge weighs these signals against the question of whether the serving
setup is production-grade.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WAREHOUSES_SQL = (
    "SELECT warehouse_type, channel_name, auto_stop_mins, "
    "min_num_clusters, max_num_clusters, COUNT(*) AS cnt "
    "FROM system.compute.warehouses "
    "GROUP BY warehouse_type, channel_name, auto_stop_mins, "
    "min_num_clusters, max_num_clusters "
    "ORDER BY cnt DESC "
    "LIMIT 20"
)

_EVENTS_SQL = (
    "SELECT event_type, COUNT(*) AS cnt "
    "FROM system.compute.warehouse_events "
    "WHERE event_time >= current_timestamp() - INTERVAL 7 DAYS "
    "GROUP BY event_type "
    "ORDER BY cnt DESC"
)

_NOTE = (
    "Production-grade SQL serving requires channel stability (CHANNEL_NAME_CURRENT not "
    "CHANNEL_NAME_PREVIEW), appropriate warehouse type (SERVERLESS or PRO for production "
    "workloads), reasonable auto-stop configuration, and dedicated capacity where needed. "
    "Whether a warehouse is intentionally dedicated to production vs shared dev/test use "
    "is not visible in system tables and requires manual confirmation."
)

_REF = "https://docs.databricks.com/en/compute/sql-warehouse/create-sql-warehouse.html"


@register(layer="analytics", question_ids=["ANA-R-02"])
class ProductionServingCheck(Check):
    """Assess production-grade SQL warehouse serving configuration.

    Evidence:
      1. Warehouse fleet breakdown by type/channel/auto_stop/cluster config.
      2. Recent warehouse event counts (last 7 days) for availability signal.
      3. A note recording what cannot be determined from system tables.
    The LLM judge weighs all three pieces.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        warehouse_rows = ctx.sql.query(_WAREHOUSES_SQL)
        event_rows = ctx.sql.query(_EVENTS_SQL)

        total_warehouses = sum(int(r.get("cnt") or 0) for r in warehouse_rows)
        preview_count = sum(
            int(r.get("cnt") or 0)
            for r in warehouse_rows
            if str(r.get("channel_name") or "").upper() == "CHANNEL_NAME_PREVIEW"
        )
        pro_or_serverless = sum(
            int(r.get("cnt") or 0)
            for r in warehouse_rows
            if str(r.get("warehouse_type") or "").upper() in ("PRO", "SERVERLESS")
        )

        if total_warehouses == 0:
            warehouse_summary = "No SQL warehouses found in system.compute.warehouses"
        else:
            warehouse_summary = (
                f"{total_warehouses} SQL warehouse(s) found: "
                f"{pro_or_serverless} PRO/SERVERLESS (managed reliability), "
                f"{preview_count} on CHANNEL_NAME_PREVIEW (non-stable channel)"
            )

        warehouse_evidence = Evidence(
            kind="sql",
            summary=warehouse_summary,
            detail=_WAREHOUSES_SQL,
            rows=warehouse_rows[:20],
            ref=_REF,
        )

        if event_rows:
            event_summary = (
                "Warehouse events (last 7 days): "
                + ", ".join(f"{r['event_type']}={r['cnt']}" for r in event_rows[:10])
            )
        else:
            event_summary = (
                "No warehouse events found in system.compute.warehouse_events "
                "for the last 7 days"
            )

        event_evidence = Evidence(
            kind="sql",
            summary=event_summary,
            detail=_EVENTS_SQL,
            rows=event_rows[:10],
            ref="https://docs.databricks.com/en/admin/system-tables/compute.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [warehouse_evidence, event_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
