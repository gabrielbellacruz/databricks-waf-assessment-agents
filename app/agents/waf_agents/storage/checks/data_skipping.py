"""Data-skipping check (LLM-judged).

Answers:
  STO-PE-03  Enable data skipping and statistics on stored tables

Delta automatically collects statistics on the first 32 columns of each table
at write time, enabling data-skipping by default.  The strength of skipping
depends on statistics coverage being kept fresh via ANALYZE TABLE ... COMPUTE
STATISTICS, and on tables having suitable column order and Z-order/clustering.

Observable proxies in system.query.history (last 30 days):
  - ANALYZE TABLE ... COMPUTE STATISTICS statements (explicit stats refresh)
  - ZORDER BY / CLUSTER BY statements (layout that amplifies skipping)

The absence of ANALYZE does not mean skipping is disabled (Delta auto-collects
stats by default), but its presence confirms proactive statistics management.
This nuance is explained in the note evidence so the LLM judge can weigh it
correctly.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """
SELECT
  SUM(CASE WHEN statement_text ILIKE '%COMPUTE STATISTICS%' THEN 1 ELSE 0 END)
      AS analyze_stmts,
  SUM(CASE WHEN statement_text ILIKE '%ANALYZE TABLE%' THEN 1 ELSE 0 END)
      AS analyze_table_stmts,
  SUM(CASE WHEN statement_text ILIKE '%ZORDER BY%'
            OR statement_text ILIKE '%CLUSTER BY%' THEN 1 ELSE 0 END)
      AS layout_stmts,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS
""".strip()

_NOTE = (
    "Delta Lake automatically collects statistics on the first 32 columns at write "
    "time (default dataSkippingNumIndexedCols=32), so data skipping is enabled by "
    "default for Delta tables. ANALYZE TABLE ... COMPUTE STATISTICS refreshes stale "
    "stats and is a positive signal; its absence does not prove skipping is off. "
    "The actual dataSkippingNumIndexedCols property and per-table statistics coverage "
    "are not exposed in system.information_schema and require manual confirmation via "
    "DESCRIBE DETAIL or the Delta transaction log."
)

_REF = "https://docs.databricks.com/en/delta/optimizations/file-mgmt.html"


@register(layer="storage", question_ids=["STO-PE-03"])
class DataSkippingCheck(Check):
    """Assess data-skipping / statistics posture via query history (last 30 days).

    Evidence is gathered from system.query.history:
      1. ANALYZE TABLE ... COMPUTE STATISTICS statement counts (explicit stats
         refresh).
      2. ZORDER BY / CLUSTER BY statement counts (layout amplifying skipping).
    A note evidence explains the Delta default behavior and the observability gap.
    The LLM judge weighs all three pieces.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            analyze_stmts = int(row.get("analyze_stmts") or 0)
            analyze_table_stmts = int(row.get("analyze_table_stmts") or 0)
            layout_stmts = int(row.get("layout_stmts") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
        else:
            analyze_stmts = 0
            analyze_table_stmts = 0
            layout_stmts = 0
            total_stmts = 0

        if total_stmts == 0:
            sql_summary = (
                "No query-history rows found for the last 30 days"
                " — cannot assess statistics / data-skipping commands"
            )
        else:
            sql_summary = (
                f"Statistics/skipping commands (last 30 days):"
                f" COMPUTE STATISTICS={analyze_stmts},"
                f" ANALYZE TABLE={analyze_table_stmts},"
                f" layout (ZORDER/CLUSTER BY)={layout_stmts};"
                f" total statements={total_stmts}"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=sql_summary,
            detail=_SQL,
            rows=[
                {
                    "analyze_stmts": analyze_stmts,
                    "analyze_table_stmts": analyze_table_stmts,
                    "layout_stmts": layout_stmts,
                    "total_stmts": total_stmts,
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

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
