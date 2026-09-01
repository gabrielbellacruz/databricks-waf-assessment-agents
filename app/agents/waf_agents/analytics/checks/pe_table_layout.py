"""Table layout optimization check (LLM-judged).

Answers:
  ANA-PE-02  Optimize table layout for analytics queries

Analytics query performance depends on table layout: clustering keys (liquid
clustering or Z-order), compaction (OPTIMIZE), and statistics for data
skipping. Observable proxies in the available system tables:

  - ``system.query.history``: OPTIMIZE, ZORDER BY, and CLUSTER BY statement
    counts indicate that layout maintenance is being performed (last 30 days).
  - ``system.information_schema.tables``: Delta table count confirms that layout
    tooling (OPTIMIZE, liquid clustering) is available for the tables in scope.

What is NOT observable: per-table clustering key definitions, whether OPTIMIZE
runs on a regular schedule, or whether clustering keys match query filter
predicates. DESCRIBE DETAIL on individual tables is required for full
confirmation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_LAYOUT_SQL = (
    "SELECT "
    "SUM(CASE WHEN statement_text ILIKE '%OPTIMIZE%' THEN 1 ELSE 0 END) AS optimize_stmts, "
    "SUM(CASE WHEN statement_text ILIKE '%ZORDER BY%' THEN 1 ELSE 0 END) AS zorder_stmts, "
    "SUM(CASE WHEN statement_text ILIKE '%CLUSTER BY%' THEN 1 ELSE 0 END) AS cluster_by_stmts, "
    "COUNT(*) AS total_stmts "
    "FROM system.query.history "
    "WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS"
)

_DELTA_TABLES_SQL = (
    "SELECT COUNT(*) AS total_tables, "
    "SUM(CASE WHEN data_source_format = 'DELTA' THEN 1 ELSE 0 END) AS delta_tables "
    "FROM system.information_schema.tables "
    "WHERE table_type IN ('MANAGED', 'EXTERNAL') "
    "AND table_catalog <> 'hive_metastore'"
)

_NOTE = (
    "Table layout optimization for analytics requires regular OPTIMIZE runs (for compaction "
    "and Z-order) or liquid clustering (CLUSTER BY, available in Delta 3.0+). OPTIMIZE and "
    "ZORDER BY counts in query history confirm that maintenance is performed, but do not "
    "reveal whether clustering keys are aligned with typical analytics filter predicates. "
    "Per-table clustering configuration is only visible via DESCRIBE DETAIL or the Delta "
    "transaction log, requiring manual confirmation for a complete assessment."
)

_REF = "https://docs.databricks.com/en/delta/clustering.html"


@register(layer="analytics", question_ids=["ANA-PE-02"])
class TableLayoutCheck(Check):
    """Assess table layout optimization for analytics via query history patterns.

    Evidence:
      1. OPTIMIZE / ZORDER BY / CLUSTER BY statement counts from query.history
         (last 30 days).
      2. Delta table adoption from information_schema (prerequisite for layout
         optimization tooling).
      3. A note recording what cannot be determined without DESCRIBE DETAIL.
    The LLM judge weighs all three pieces.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        layout_rows = ctx.sql.query(_LAYOUT_SQL)
        delta_rows = ctx.sql.query(_DELTA_TABLES_SQL)

        if layout_rows:
            row = layout_rows[0]
            optimize_stmts = int(row.get("optimize_stmts") or 0)
            zorder_stmts = int(row.get("zorder_stmts") or 0)
            cluster_by_stmts = int(row.get("cluster_by_stmts") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
        else:
            optimize_stmts = 0
            zorder_stmts = 0
            cluster_by_stmts = 0
            total_stmts = 0

        if total_stmts == 0:
            layout_summary = (
                "No query history found for the last 30 days "
                "— cannot assess layout optimization commands"
            )
        else:
            layout_summary = (
                f"Layout optimization commands (last 30 days): "
                f"OPTIMIZE={optimize_stmts}, ZORDER BY={zorder_stmts}, "
                f"CLUSTER BY={cluster_by_stmts}; total statements={total_stmts}"
            )

        layout_evidence = Evidence(
            kind="sql",
            summary=layout_summary,
            detail=_LAYOUT_SQL,
            rows=[{
                "optimize_stmts": optimize_stmts,
                "zorder_stmts": zorder_stmts,
                "cluster_by_stmts": cluster_by_stmts,
                "total_stmts": total_stmts,
            }],
            ref=_REF,
        )

        if delta_rows:
            dr = delta_rows[0]
            total_tables = int(dr.get("total_tables") or 0)
            delta_tables = int(dr.get("delta_tables") or 0)
            pct = round(100.0 * delta_tables / total_tables, 1) if total_tables > 0 else 0.0
            delta_summary = (
                f"{delta_tables} of {total_tables} managed/external tables ({pct}%) "
                "use Delta — layout optimization tooling (OPTIMIZE/liquid clustering) available"
            )
        else:
            total_tables = 0
            delta_tables = 0
            delta_summary = "No table metadata found in system.information_schema.tables"

        delta_evidence = Evidence(
            kind="sql",
            summary=delta_summary,
            detail=_DELTA_TABLES_SQL,
            rows=[{"total_tables": total_tables, "delta_tables": delta_tables}],
            ref="https://docs.databricks.com/en/delta/optimize.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [layout_evidence, delta_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
