"""Data quality standards check (LLM-judged).

Answers:
  ING-DG-05  Define data quality standards for incoming data

Signal: enforced table constraints in Unity Catalog (system.information_schema.check_constraints
and system.information_schema.table_constraints) are a partial proxy for whether data-quality
standards have been formalised. The total number of governed tables provides context for
interpreting low constraint counts. A note evidence records the key gap: DLT/Lakeflow
pipeline expectations and source-level quality SLAs are not visible in system tables, so the
LLM judge weighs both the numeric signal and the limitation caveat.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_CHECK_CONSTRAINTS_SQL = (
    "SELECT COUNT(*) AS check_constraints "
    "FROM system.information_schema.check_constraints"
)

_TABLE_CONSTRAINTS_SQL = (
    "SELECT COUNT(*) AS table_constraints "
    "FROM system.information_schema.table_constraints"
)

_TABLES_SQL = (
    "SELECT COUNT(*) AS total_tables "
    "FROM system.information_schema.tables "
    "WHERE table_type IN ('MANAGED','EXTERNAL') "
    "  AND table_catalog <> 'hive_metastore'"
)

_NOTE = (
    "DLT/Lakeflow pipeline *expectations* and agreed source-level quality SLAs are not exposed "
    "in system tables; enforced table/check constraints are only a partial proxy, so a low count "
    "does not by itself prove quality standards are absent — manual confirmation needed."
)

_REF = "https://docs.databricks.com/en/tables/constraints.html"


@register(layer="ingestion", question_ids=["ING-DG-05"])
class DataQualityStandardsCheck(Check):
    """LLM-judged check: whether the workspace has defined data-quality standards for incoming data.

    Evidence is gathered purely from system.information_schema: enforced check constraints and
    table constraints serve as a partial observable proxy. A note records that pipeline-level
    quality expectations (DLT/Lakeflow) and agreed source SLAs are not visible in system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        check_rows = ctx.sql.query(_CHECK_CONSTRAINTS_SQL)
        table_constraint_rows = ctx.sql.query(_TABLE_CONSTRAINTS_SQL)
        tables_rows = ctx.sql.query(_TABLES_SQL)

        check_count = int(
            (check_rows[0].get("check_constraints") or 0) if check_rows else 0
        )
        table_constraint_count = int(
            (table_constraint_rows[0].get("table_constraints") or 0) if table_constraint_rows else 0
        )
        total_tables = int(
            (tables_rows[0].get("total_tables") or 0) if tables_rows else 0
        )

        summary = (
            f"{check_count} check constraint(s) and {table_constraint_count} table constraint(s) "
            f"across {total_tables} governed table(s) in Unity Catalog"
        )

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=f"{_CHECK_CONSTRAINTS_SQL}\n{_TABLE_CONSTRAINTS_SQL}\n{_TABLES_SQL}",
            rows=[
                {
                    "check_constraints": check_count,
                    "table_constraints": table_constraint_count,
                    "total_tables": total_tables,
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
