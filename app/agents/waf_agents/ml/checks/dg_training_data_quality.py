"""Training data quality check (LLM-judged).

Answers:
  ML-DG-04  Ensure quality of training data

Signals:
  * ``system.information_schema.check_constraints`` — enforced CHECK constraints on
    tables in ML-suggestive schemas (feature*, model*, ml*, train*) are a partial proxy
    for formalised data quality standards.
  * ``system.information_schema.table_constraints`` — primary-key and other enforced
    constraints on the same tables.
  * ``system.information_schema.tables`` — total count of ML-suggestive UC tables,
    providing context for interpreting low constraint counts.
  * Note: DLT/Lakeflow pipeline *expectations* applied to feature-generation pipelines,
    and agreed source-level quality SLAs, are not visible in system tables. A low
    constraint count does not prove quality standards are absent — manual confirmation needed.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

# CHECK constraints on ML-related tables.
_ML_CHECK_CONSTRAINTS_SQL = (
    "SELECT COUNT(*) AS ml_check_constraints "
    "FROM system.information_schema.check_constraints cc "
    "JOIN system.information_schema.tables t "
    "  ON cc.constraint_catalog = t.table_catalog "
    "  AND cc.constraint_schema = t.table_schema "
    "WHERE t.table_catalog <> 'hive_metastore' "
    "  AND (LOWER(t.table_schema) LIKE '%feature%' "
    "       OR LOWER(t.table_schema) LIKE '%model%' "
    "       OR LOWER(t.table_schema) LIKE '%ml%' "
    "       OR LOWER(t.table_schema) LIKE '%train%')"
)

# Table constraints (PK / FK / NOT NULL) on ML-related tables.
_ML_TABLE_CONSTRAINTS_SQL = (
    "SELECT COUNT(*) AS ml_table_constraints "
    "FROM system.information_schema.table_constraints tc "
    "JOIN system.information_schema.tables t "
    "  ON tc.constraint_catalog = t.table_catalog "
    "  AND tc.constraint_schema = t.table_schema "
    "WHERE t.table_catalog <> 'hive_metastore' "
    "  AND (LOWER(t.table_schema) LIKE '%feature%' "
    "       OR LOWER(t.table_schema) LIKE '%model%' "
    "       OR LOWER(t.table_schema) LIKE '%ml%' "
    "       OR LOWER(t.table_schema) LIKE '%train%')"
)

# Total ML-suggestive tables in Unity Catalog.
_ML_TOTAL_TABLES_SQL = (
    "SELECT COUNT(*) AS total_ml_tables "
    "FROM system.information_schema.tables "
    "WHERE table_catalog <> 'hive_metastore' "
    "  AND table_type IN ('MANAGED','EXTERNAL') "
    "  AND (LOWER(table_schema) LIKE '%feature%' "
    "       OR LOWER(table_schema) LIKE '%model%' "
    "       OR LOWER(table_schema) LIKE '%ml%' "
    "       OR LOWER(table_schema) LIKE '%train%')"
)

_NOTE = (
    "DLT/Lakeflow pipeline expectations (e.g. EXPECT constraints in Delta Live Tables) "
    "and agreed training-data quality SLAs are not exposed in system.information_schema; "
    "enforced table/check constraints are only a partial proxy. A low constraint count "
    "does not prove that quality standards are absent — manual confirmation of pipeline-level "
    "quality rules is recommended."
)

_REF = "https://docs.databricks.com/en/tables/constraints.html"


@register(layer="ml", question_ids=["ML-DG-04"])
class MlTrainingDataQualityCheck(Check):
    """LLM-judged check for ML-DG-04: quality standards on training data."""

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        check_rows = ctx.sql.query(_ML_CHECK_CONSTRAINTS_SQL)
        table_constraint_rows = ctx.sql.query(_ML_TABLE_CONSTRAINTS_SQL)
        total_rows = ctx.sql.query(_ML_TOTAL_TABLES_SQL)

        ml_check_constraints = int(
            (check_rows[0].get("ml_check_constraints") or 0) if check_rows else 0
        )
        ml_table_constraints = int(
            (table_constraint_rows[0].get("ml_table_constraints") or 0)
            if table_constraint_rows
            else 0
        )
        total_ml_tables = int(
            (total_rows[0].get("total_ml_tables") or 0) if total_rows else 0
        )

        sql_evidence = Evidence(
            kind="sql",
            summary=(
                f"{ml_check_constraints} check constraint(s) and "
                f"{ml_table_constraints} table constraint(s) across "
                f"{total_ml_tables} ML-suggestive UC table(s)"
            ),
            detail=(
                f"{_ML_CHECK_CONSTRAINTS_SQL}\n"
                f"{_ML_TABLE_CONSTRAINTS_SQL}\n"
                f"{_ML_TOTAL_TABLES_SQL}"
            ),
            rows=[
                {
                    "ml_check_constraints": ml_check_constraints,
                    "ml_table_constraints": ml_table_constraints,
                    "total_ml_tables": total_ml_tables,
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
