"""Format and definition standardization in transformations (LLM-judged).

Answers:
  PRO-DG-05  Standardize formats and definitions in transformations

Signal: shared-dimension column-name consistency from
``system.information_schema.columns``.  Column names that recur across many
tables are treated as shared dimensions; type inconsistencies among those
columns (e.g. ``customer_id`` appearing as STRING in some tables and BIGINT
in others) indicate that transformations have not standardised definitions.
A workspace-wide count of column names mapped to more than one data_type
provides a broader inconsistency signal.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

# Column names that appear in this many or more distinct tables are considered
# shared dimensions and are checked for type consistency.
_MIN_TABLE_COUNT = 5

_RECURRING_COLUMNS_SQL = (
    "SELECT column_name, "
    "COUNT(DISTINCT table_catalog || '.' || table_schema || '.' || table_name) AS table_count, "
    "COUNT(DISTINCT data_type) AS type_count "
    "FROM system.information_schema.columns "
    "WHERE table_catalog <> 'hive_metastore' "
    "GROUP BY column_name "
    f"HAVING COUNT(DISTINCT table_catalog || '.' || table_schema || '.' || table_name) "
    f"> {_MIN_TABLE_COUNT} "
    "ORDER BY table_count DESC "
    "LIMIT 50"
)

_INCONSISTENT_COLUMNS_SQL = (
    "SELECT COUNT(DISTINCT column_name) AS inconsistent_columns "
    "FROM ("
    " SELECT column_name "
    " FROM system.information_schema.columns "
    " WHERE table_catalog <> 'hive_metastore' "
    " GROUP BY column_name "
    " HAVING COUNT(DISTINCT data_type) > 1"
    ") sub"
)

_REF = "https://docs.databricks.com/en/data-governance/unity-catalog/best-practices.html"


@register(layer="processing", question_ids=["PRO-DG-05"])
class ProcessingFormatStandardizationCheck(Check):
    """Assess standardisation of formats and definitions across transformations.

    Evidence is gathered from ``system.information_schema.columns``:
      1. Column names recurring across many tables and their type consistency.
      2. Workspace-wide count of column names that map to more than one
         distinct data_type (direct inconsistency signal).

    The LLM judge weighs both signals to decide whether shared definitions
    are standardised across the transformation estate.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        recurring_rows = ctx.sql.query(_RECURRING_COLUMNS_SQL)
        inconsistent_rows = ctx.sql.query(_INCONSISTENT_COLUMNS_SQL)

        inconsistent_count = int(
            (inconsistent_rows[0].get("inconsistent_columns") or 0) if inconsistent_rows else 0
        )
        mixed_type_cols = [r for r in recurring_rows if int(r.get("type_count") or 1) > 1]

        recurring_evidence = Evidence(
            kind="sql",
            summary=(
                f"{len(recurring_rows)} shared-dimension column name(s) appear "
                f"in >{_MIN_TABLE_COUNT} tables; "
                f"{len(mixed_type_cols)} of those have inconsistent data types"
            ),
            detail=_RECURRING_COLUMNS_SQL,
            rows=recurring_rows[:25],
            ref=_REF,
        )
        inconsistent_evidence = Evidence(
            kind="sql",
            summary=(
                f"{inconsistent_count} column name(s) workspace-wide "
                "map to more than one distinct data_type across UC tables"
            ),
            detail=_INCONSISTENT_COLUMNS_SQL,
            rows=inconsistent_rows[:5],
            ref=_REF,
        )
        return [recurring_evidence, inconsistent_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
