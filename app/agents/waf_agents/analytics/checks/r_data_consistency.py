"""Analytics data consistency check (LLM-judged).

Answers:
  ANA-R-03  Ensure consistency of served analytics data

Consistent analytics data means dashboards and reports reflect a coherent,
up-to-date snapshot — not a mix of stale and fresh values. The primary
mechanism in Databricks is materialized views (refreshed atomically) or Delta
tables with ACID guarantees combined with scheduled refreshes.

Observable proxies from system tables:
  - ``system.query.history``: REFRESH MATERIALIZED VIEW statements signal that
    materialized views are being used and regularly refreshed.
  - ``system.information_schema.tables``: count of tables available to analytics
    layers (Delta format guarantees ACID reads).
  - ``system.query.history``: CREATE MATERIALIZED VIEW statements to gauge MV
    adoption.

What is NOT observable: whether dashboards query materialized views vs base
tables, whether cache invalidation is coordinated, or whether a single
consistent snapshot is enforced at query time. Manual confirmation required.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_MV_REFRESH_SQL = (
    "SELECT "
    "SUM(CASE WHEN statement_text ILIKE '%REFRESH MATERIALIZED VIEW%' THEN 1 ELSE 0 END) "
    "AS refresh_mv_stmts, "
    "SUM(CASE WHEN statement_text ILIKE '%CREATE%MATERIALIZED VIEW%' THEN 1 ELSE 0 END) "
    "AS create_mv_stmts, "
    "COUNT(*) AS total_stmts "
    "FROM system.query.history "
    "WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS"
)

_DELTA_SQL = (
    "SELECT COUNT(*) AS total_tables, "
    "SUM(CASE WHEN data_source_format = 'DELTA' THEN 1 ELSE 0 END) AS delta_tables "
    "FROM system.information_schema.tables "
    "WHERE table_type IN ('MANAGED', 'EXTERNAL') "
    "AND table_catalog <> 'hive_metastore'"
)

_NOTE = (
    "Consistent analytics data requires that dashboards and reports query a coherent, "
    "up-to-date snapshot. Materialized views (REFRESH MATERIALIZED VIEW) provide "
    "atomic refresh semantics; Delta tables provide ACID read isolation. However, whether "
    "dashboards are wired to materialized views vs base tables, and whether refresh "
    "schedules are aligned across all data sources, is not visible in system tables and "
    "requires manual confirmation."
)

_REF = "https://docs.databricks.com/en/sql/language-manual/sql-ref-syntax-ddl-create-materialized-view.html"


@register(layer="analytics", question_ids=["ANA-R-03"])
class DataConsistencyCheck(Check):
    """Assess consistency of served analytics data via materialized view usage.

    Evidence:
      1. Materialized view REFRESH and CREATE statement counts from query history
         (last 30 days).
      2. Delta table adoption from information_schema (ACID read guarantees).
      3. A note recording what cannot be determined from system tables.
    The LLM judge weighs all three pieces.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        mv_rows = ctx.sql.query(_MV_REFRESH_SQL)
        delta_rows = ctx.sql.query(_DELTA_SQL)

        if mv_rows:
            row = mv_rows[0]
            refresh_mv = int(row.get("refresh_mv_stmts") or 0)
            create_mv = int(row.get("create_mv_stmts") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
        else:
            refresh_mv = 0
            create_mv = 0
            total_stmts = 0

        if total_stmts == 0:
            mv_summary = (
                "No query history found for the last 30 days "
                "— cannot assess materialized view usage"
            )
        else:
            mv_summary = (
                f"Materialized view usage (last 30 days): "
                f"REFRESH={refresh_mv}, CREATE={create_mv}; "
                f"total statements={total_stmts}"
            )

        mv_evidence = Evidence(
            kind="sql",
            summary=mv_summary,
            detail=_MV_REFRESH_SQL,
            rows=[{
                "refresh_mv_stmts": refresh_mv,
                "create_mv_stmts": create_mv,
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
                f"{delta_tables} of {total_tables} managed/external tables use Delta format "
                f"({pct}%) — ACID read isolation available"
            )
        else:
            total_tables = 0
            delta_tables = 0
            delta_summary = "No table metadata found in system.information_schema.tables"

        delta_evidence = Evidence(
            kind="sql",
            summary=delta_summary,
            detail=_DELTA_SQL,
            rows=[{"total_tables": total_tables, "delta_tables": delta_tables}],
            ref="https://docs.databricks.com/en/delta/index.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [mv_evidence, delta_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
