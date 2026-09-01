"""Redundancy-reduction check (LLM-judged).

Answers:
  STO-R-05  Reduce redundancy in stored data

Unnecessary copies of data increase storage costs, diverge over time, and
create consistency hazards.  Three evidence signals are collected:

1. Duplicate table names across schemas — tables with the same name in many
   schemas often indicate copy-paste proliferation rather than intentional
   layering.  The top offenders (by schema_count) are surfaced.

2. View-to-base-table ratio — views are a zero-copy alternative to physical
   copies; a healthy ratio indicates the team prefers computed references
   over duplicate tables.

3. CTAS (CREATE TABLE AS SELECT) frequency in ``system.query.history`` —
   a high CTAS rate suggests the team routinely materialises full copies of
   datasets rather than using views or Delta sharing, a common redundancy
   anti-pattern.

These signals are indirect proxies; the LLM judge weighs them together.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_DUPLICATE_NAMES_SQL = """\
SELECT table_name,
       COUNT(DISTINCT table_catalog || '.' || table_schema) AS schema_count
FROM system.information_schema.tables
WHERE table_type IN ('MANAGED', 'EXTERNAL')
  AND table_catalog <> 'hive_metastore'
GROUP BY table_name
HAVING COUNT(DISTINCT table_catalog || '.' || table_schema) > 1
ORDER BY schema_count DESC
LIMIT 20"""

_VIEW_RATIO_SQL = (
    "SELECT"
    " SUM(CASE WHEN table_type = 'VIEW' THEN 1 ELSE 0 END) AS view_count,"
    " SUM(CASE WHEN table_type IN ('MANAGED', 'EXTERNAL') THEN 1 ELSE 0 END)"
    "   AS base_table_count"
    " FROM system.information_schema.tables"
    " WHERE table_catalog <> 'hive_metastore'"
)

_CTAS_SQL = """\
SELECT COUNT(*) AS ctas_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS
  AND statement_text ILIKE '%CREATE TABLE%AS SELECT%'"""

_REF = "https://docs.databricks.com/en/delta/delta-sharing.html"


@register(layer="storage", question_ids=["STO-R-05"])
class ReduceRedundancyCheck(Check):
    """Assess data-copy proliferation via table-name duplication, view ratio,
    and CTAS frequency.

    Identical table names across many schemas are a strong signal of
    copy-paste duplication.  A high view ratio and low CTAS rate are positive
    signals that the team prefers logical references and incremental patterns
    over physical copies.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        dup_rows = ctx.sql.query(_DUPLICATE_NAMES_SQL)
        view_rows = ctx.sql.query(_VIEW_RATIO_SQL)
        ctas_rows = ctx.sql.query(_CTAS_SQL)

        # --- Duplicate names signal ---
        dup_count = len(dup_rows)
        top_offenders = dup_rows[:10]
        if dup_count > 0:
            dup_summary = (
                f"{dup_count} table names appear in more than one schema"
                " (potential copy-paste redundancy)."
                f" Top offender: {top_offenders[0].get('table_name', 'unknown')}"
                f" in {top_offenders[0].get('schema_count', '?')} schemas."
            )
        else:
            dup_summary = (
                "No table names found repeated across multiple schemas"
                " — no obvious name-duplication pattern detected."
            )
        dup_evidence = Evidence(
            kind="sql",
            summary=dup_summary,
            detail=_DUPLICATE_NAMES_SQL,
            rows=top_offenders,
            ref=_REF,
        )

        # --- View ratio signal ---
        view_row = view_rows[0] if view_rows else {}
        views = int(view_row.get("view_count") or 0)
        base_tables = int(view_row.get("base_table_count") or 0)
        total_objects = views + base_tables
        view_pct = round(100.0 * views / total_objects, 1) if total_objects > 0 else 0.0

        view_evidence = Evidence(
            kind="sql",
            summary=(
                f"{views} views vs {base_tables} base tables"
                f" ({view_pct}% of all table-like objects are views)."
                " Views are zero-copy; a higher ratio indicates less physical duplication."
            ),
            detail=_VIEW_RATIO_SQL,
            rows=[
                {
                    "view_count": views,
                    "base_table_count": base_tables,
                    "view_pct": view_pct,
                }
            ],
            ref=_REF,
        )

        # --- CTAS signal ---
        ctas = int((ctas_rows[0].get("ctas_stmts") or 0) if ctas_rows else 0)
        ctas_evidence = Evidence(
            kind="sql",
            summary=(
                f"{ctas} CREATE TABLE AS SELECT statements in the last 30 days."
                " Frequent CTAS usage may indicate routine full-copy materialisation"
                " rather than incremental or view-based patterns."
            ),
            detail=_CTAS_SQL,
            rows=[{"ctas_stmts": ctas}],
            ref=_REF,
        )

        return [dup_evidence, view_evidence, ctas_evidence]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
