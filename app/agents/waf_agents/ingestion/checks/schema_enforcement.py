"""Schema enforcement check (LLM-judged).

Answers:
  ING-R-04  Enforce schema on incoming data

Signal: Delta tables enforce schema on write by default, so the ratio of
Delta tables to all managed/external tables is a baseline proxy for schema
enforcement. Declared table constraints (NOT NULL, CHECK) from
``system.information_schema.table_constraints`` are an additional explicit-
enforcement signal. Neither captures Auto Loader schema-evolution mode nor DLT
expectations, so a note evidence records that gap and the LLM judge weighs both
pieces together.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_TABLES_SQL = """\
SELECT COUNT(*) AS total_tables,
       SUM(CASE WHEN data_source_format = 'DELTA' THEN 1 ELSE 0 END) AS delta_tables
FROM system.information_schema.tables
WHERE table_type IN ('MANAGED','EXTERNAL') AND table_catalog <> 'hive_metastore'\
"""

_CONSTRAINTS_SQL = """\
SELECT COUNT(*) AS declared_constraints FROM system.information_schema.table_constraints\
"""

_NOTE = (
    "Delta enforces schema-on-write by default, so a high Delta share implies baseline "
    "schema enforcement; Auto Loader schema-evolution mode and explicit expectations are "
    "not visible in system tables. Treat this as a baseline proxy."
)

_REF = "https://docs.databricks.com/en/tables/constraints.html"


@register(layer="ingestion", question_ids=["ING-R-04"])
class SchemaEnforcementCheck(Check):
    """Assess schema enforcement via Delta table share and declared constraints.

    Queries ``system.information_schema.tables`` for the ratio of Delta tables
    to all managed/external tables (Delta enforces schema on write by default)
    and ``system.information_schema.table_constraints`` for explicitly declared
    constraints (NOT NULL, CHECK). Both counts are passed to the LLM judge with
    a note recording that Auto Loader evolution mode and DLT expectations are
    not visible in system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        table_rows = ctx.sql.query(_TABLES_SQL)
        constraint_rows = ctx.sql.query(_CONSTRAINTS_SQL)

        if table_rows:
            total_tables = int(table_rows[0].get("total_tables") or 0)
            delta_tables = int(table_rows[0].get("delta_tables") or 0)
        else:
            total_tables = 0
            delta_tables = 0

        if constraint_rows:
            declared_constraints = int(constraint_rows[0].get("declared_constraints") or 0)
        else:
            declared_constraints = 0

        if total_tables > 0:
            delta_pct = round(100.0 * delta_tables / total_tables, 1)
            sql_summary = (
                f"{delta_tables} of {total_tables} managed/external tables use Delta "
                f"({delta_pct}%); {declared_constraints} explicit table constraints declared"
            )
        else:
            sql_summary = (
                f"No managed/external tables found outside hive_metastore; "
                f"{declared_constraints} explicit table constraints declared"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=sql_summary,
            detail=_TABLES_SQL,
            rows=[
                {
                    "total_tables": total_tables,
                    "delta_tables": delta_tables,
                    "declared_constraints": declared_constraints,
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

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
