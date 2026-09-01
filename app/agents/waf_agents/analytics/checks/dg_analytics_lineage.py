"""Analytics lineage coverage check (LLM-judged).

Answers:
  ANA-DG-04  Expose lineage from dashboards to sources

Signals:
  * ``system.access.table_lineage`` — count of target tables with upstream lineage
    edges tracked in the last 30 days, and the total edge count.  Tables queried
    through SQL warehouses and Databricks SQL dashboards generate lineage events
    here, so a non-zero edge count indicates lineage is being captured for analytics
    workloads.
  * Total UC tables count from ``system.information_schema.tables`` to provide
    lineage coverage context.

Limitation: end-to-end dashboard-to-source lineage (which dashboard queries which
table) is not directly exposed as a single artifact in system tables.  The
``system.access.table_lineage`` view captures table-to-table dependencies at the
SQL-execution level; dashboard-level attribution requires the Databricks Lineage
Graph API which is not accessible to the agent SP's system-table queries.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_LINEAGE_SQL = (
    "SELECT COUNT(DISTINCT target_table_full_name) AS tables_with_lineage,"
    " COUNT(*) AS total_lineage_edges"
    " FROM system.access.table_lineage"
    " WHERE event_time > current_timestamp() - INTERVAL 30 DAYS"
)

_UC_TABLE_COUNT_SQL = (
    "SELECT COUNT(*) AS uc_table_count"
    " FROM system.information_schema.tables"
    " WHERE table_type IN ('MANAGED','EXTERNAL','VIEW','MATERIALIZED_VIEW')"
    " AND table_catalog <> 'hive_metastore'"
)

_LINEAGE_LIMITATION = (
    "system.access.table_lineage captures SQL-execution-level lineage (which table"
    " was read to produce which table); end-to-end dashboard-to-source lineage is"
    " not exposed as a single row.  Zero results may mean Unity Catalog lineage"
    " tracking is disabled or no warehouse queries ran in the last 30 days."
)

_REF = "https://docs.databricks.com/en/data-governance/unity-catalog/data-lineage.html"


@register(layer="analytics", question_ids=["ANA-DG-04"])
class AnalyticsLineageCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        lineage_rows = ctx.sql.query(_LINEAGE_SQL)
        uc_rows = ctx.sql.query(_UC_TABLE_COUNT_SQL)

        lrow = lineage_rows[0] if lineage_rows else {}
        tables_with_lineage = int(lrow.get("tables_with_lineage") or 0)
        total_lineage_edges = int(lrow.get("total_lineage_edges") or 0)

        uc_table_count = int(
            (uc_rows[0].get("uc_table_count") or 0) if uc_rows else 0
        )

        lineage_evidence = Evidence(
            kind="sql",
            summary=(
                f"{tables_with_lineage} UC table(s) have upstream lineage tracked"
                f" in the last 30 days ({total_lineage_edges} total edges)"
            ),
            detail=_LINEAGE_SQL,
            rows=lineage_rows[:5],
            ref=_REF,
        )
        coverage_evidence = Evidence(
            kind="sql",
            summary=(
                f"{uc_table_count} total managed/external/view objects in UC;"
                " lineage coverage is"
                f" {round(100.0 * tables_with_lineage / uc_table_count, 1) if uc_table_count else 0}%"  # noqa: E501
            ),
            detail=_UC_TABLE_COUNT_SQL,
            rows=uc_rows[:3],
            ref=_REF,
        )
        limitation_evidence = Evidence(
            kind="uc_metadata",
            summary=_LINEAGE_LIMITATION,
            detail=(
                "To view full lineage graph, use the Databricks Unity Catalog Lineage"
                " Graph UI or the Lineage Graph REST API."
            ),
            ref=_REF,
        )
        return [lineage_evidence, coverage_evidence, limitation_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
