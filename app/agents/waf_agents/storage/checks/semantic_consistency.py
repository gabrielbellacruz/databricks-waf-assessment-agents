"""Semantic consistency across domains check (LLM-judged).

Answers:
  STO-IU-05  Keep stored data semantically consistent across domains

Signal: from ``system.information_schema.columns``, shared-dimension column names
that recur across many tables are identified and their type consistency is checked.

  * Column names appearing in more than ``_MIN_TABLE_COUNT`` distinct tables are
    treated as shared dimensions; among those, columns mapping to more than one
    distinct ``data_type`` are inconsistency signals
    (e.g. ``customer_id`` appearing as both STRING and BIGINT).
  * A workspace-wide count of column names with more than one distinct data_type
    provides a broader inconsistency signal.

The LLM judge receives both signals and decides whether shared dimensions are
semantically consistent across domain boundaries.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

# Column names recurring across at least this many distinct tables are treated as
# shared dimensions worth checking for type consistency.
_MIN_TABLE_COUNT = 5

_RECURRING_COLUMNS_SQL = (
    "SELECT column_name,"
    " COUNT(DISTINCT table_catalog || '.' || table_schema || '.' || table_name) AS table_count,"
    " COUNT(DISTINCT data_type) AS type_count"
    " FROM system.information_schema.columns"
    " WHERE table_catalog <> 'hive_metastore'"
    " GROUP BY column_name"
    f" HAVING COUNT(DISTINCT table_catalog || '.' || table_schema || '.' || table_name)"
    f" > {_MIN_TABLE_COUNT}"
    " ORDER BY table_count DESC"
    " LIMIT 50"
)

_INCONSISTENT_COLUMNS_SQL = (
    "SELECT COUNT(DISTINCT column_name) AS inconsistent_columns"
    " FROM ("
    "  SELECT column_name"
    "  FROM system.information_schema.columns"
    "  WHERE table_catalog <> 'hive_metastore'"
    "  GROUP BY column_name"
    "  HAVING COUNT(DISTINCT data_type) > 1"
    " ) sub"
)

_REF = "https://docs.databricks.com/en/data-governance/unity-catalog/best-practices.html"


@register(layer="storage", question_ids=["STO-IU-05"])
class SemanticConsistencyCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        recurring_rows = ctx.sql.query(_RECURRING_COLUMNS_SQL)
        inconsistent_rows = ctx.sql.query(_INCONSISTENT_COLUMNS_SQL)

        inconsistent_count = int(
            (inconsistent_rows[0].get("inconsistent_columns") or 0) if inconsistent_rows else 0
        )

        # Shared-dimension columns that already show type inconsistency are the clearest signal.
        mixed_type_cols = [r for r in recurring_rows if int(r.get("type_count") or 1) > 1]

        recurring_evidence = Evidence(
            kind="sql",
            summary=(
                f"{len(recurring_rows)} column name(s) recur across >{_MIN_TABLE_COUNT} tables;"
                f" {len(mixed_type_cols)} of those have inconsistent data types"
            ),
            detail=_RECURRING_COLUMNS_SQL,
            rows=recurring_rows[:25],
            ref=_REF,
        )
        inconsistent_evidence = Evidence(
            kind="sql",
            summary=(
                f"{inconsistent_count} column name(s) workspace-wide"
                " map to more than one distinct data_type across tables"
            ),
            detail=_INCONSISTENT_COLUMNS_SQL,
            rows=inconsistent_rows[:5],
            ref=_REF,
        )
        return [recurring_evidence, inconsistent_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
