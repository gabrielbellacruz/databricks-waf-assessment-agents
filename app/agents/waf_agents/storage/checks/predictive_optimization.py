"""Predictive Optimization check (LLM-judged).

Answers:
  STO-PE-04  Enable Predictive Optimization for stored tables

Predictive Optimization (PO) is a Databricks-managed service that automatically
runs OPTIMIZE and VACUUM on Delta tables when it determines they will benefit,
eliminating the need for manual maintenance jobs.  Whether PO is enabled is
stored in workspace/catalog/table configuration that is not exposed in
system.information_schema or system.query.history.

Proxies used by this check (both weak, per the signal-access note):
  1. Near-absence of manual OPTIMIZE/VACUUM in query history: if PO is active,
     these should be rare or absent because PO runs them automatically.
  2. Delta table adoption share from system.information_schema.tables: PO only
     applies to Delta tables, so a high Delta share is a necessary (not
     sufficient) condition.

The check is honest about the weak-signal nature; the LLM judge is expected to
return unknown or low-confidence verdicts unless the signal is very clear.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_MAINTENANCE = """
SELECT
  SUM(CASE WHEN statement_text ILIKE '%OPTIMIZE%' THEN 1 ELSE 0 END)
      AS optimize_stmts,
  SUM(CASE WHEN statement_text ILIKE '%VACUUM%' THEN 1 ELSE 0 END)
      AS vacuum_stmts,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS
""".strip()

_SQL_DELTA = (
    "SELECT COUNT(*) AS total_tables,"
    " SUM(CASE WHEN data_source_format = 'DELTA' THEN 1 ELSE 0 END) AS delta_tables"
    " FROM system.information_schema.tables"
    " WHERE table_type IN ('MANAGED','EXTERNAL') AND table_catalog <> 'hive_metastore'"
)

_NOTE = (
    "Predictive Optimization (PO) enablement is stored in workspace/catalog/table "
    "configuration that is not exposed in system.information_schema or "
    "system.query.history.  This check uses two weak proxies: (1) near-absence of "
    "manual OPTIMIZE/VACUUM commands (PO would run them automatically), and (2) Delta "
    "table share (PO requires Delta).  These are insufficient to confirm PO is enabled; "
    "a reviewer must verify via the Databricks UI (Catalog Explorer > table properties) or the "
    "REST API."
)

_REF = "https://docs.databricks.com/en/optimizations/predictive-optimization.html"


@register(layer="storage", question_ids=["STO-PE-04"])
class PredictiveOptimizationCheck(Check):
    """Assess Predictive Optimization adoption via weak proxy signals.

    Evidence is gathered from two sources:
      1. system.query.history (last 30 days): counts of manual OPTIMIZE/VACUUM
         commands — their absence may indicate PO is handling maintenance.
      2. system.information_schema.tables: Delta table share — PO requires Delta.
    A note evidence records that PO enablement flags are not directly observable.
    The LLM judge is expected to return unknown/low where signals are thin.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        maint_rows = ctx.sql.query(_SQL_MAINTENANCE)
        delta_rows = ctx.sql.query(_SQL_DELTA)

        if maint_rows:
            row = maint_rows[0]
            optimize_stmts = int(row.get("optimize_stmts") or 0)
            vacuum_stmts = int(row.get("vacuum_stmts") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
        else:
            optimize_stmts = 0
            vacuum_stmts = 0
            total_stmts = 0

        if total_stmts == 0:
            maint_summary = (
                "No query-history rows found for the last 30 days"
                " — cannot assess manual maintenance command frequency"
            )
        else:
            maint_summary = (
                f"Manual maintenance commands (last 30 days): OPTIMIZE={optimize_stmts},"
                f" VACUUM={vacuum_stmts}; total statements={total_stmts}."
                " (Low counts may indicate Predictive Optimization is managing"
                " maintenance.)"
            )

        maint_evidence = Evidence(
            kind="sql",
            summary=maint_summary,
            detail=_SQL_MAINTENANCE,
            rows=[
                {
                    "optimize_stmts": optimize_stmts,
                    "vacuum_stmts": vacuum_stmts,
                    "total_stmts": total_stmts,
                }
            ],
            ref=_REF,
        )

        if delta_rows:
            row = delta_rows[0]
            total_tables = int(row.get("total_tables") or 0)
            delta_tables = int(row.get("delta_tables") or 0)
        else:
            total_tables = 0
            delta_tables = 0

        pct = round(100.0 * delta_tables / total_tables, 1) if total_tables > 0 else 0.0
        delta_summary = (
            f"{delta_tables} of {total_tables} managed/external tables use Delta format"
            f" ({pct}%) — Predictive Optimization applies to Delta tables only"
        )

        delta_evidence = Evidence(
            kind="sql",
            summary=delta_summary,
            detail=_SQL_DELTA,
            rows=[
                {
                    "total_tables": total_tables,
                    "delta_tables": delta_tables,
                    "delta_pct": pct,
                }
            ],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [maint_evidence, delta_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
