"""Sensitive data classification check for storage layer (LLM-judged).

Answers:
  STO-DG-05  Classify sensitive stored data for masking

Signal: column-level tag coverage from ``system.information_schema.column_tags``
(tagged columns, tagged tables) vs total column count from
``system.information_schema.columns`` (excluding hive_metastore), plus the count
of tags whose name or value suggests a sensitivity classification
(ILIKE '%pii%', '%sensitive%', '%confidential%', '%gdpr%', '%classification%').
The LLM judge decides whether sensitive data is adequately classified for masking.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_COLUMN_TAG_COVERAGE_SQL = (
    "SELECT COUNT(*) AS tagged_columns,"
    " COUNT(DISTINCT catalog_name||'.'||schema_name||'.'||table_name) AS tagged_tables"
    " FROM system.information_schema.column_tags"
)

_SENSITIVITY_TAGS_SQL = (
    "SELECT COUNT(*) AS sensitivity_tag_count,"
    " COUNT(DISTINCT catalog_name||'.'||schema_name||'.'||table_name)"
    "   AS sensitivity_tagged_tables"
    " FROM system.information_schema.column_tags"
    " WHERE tag_name ILIKE '%pii%'"
    "    OR tag_name ILIKE '%sensitive%'"
    "    OR tag_name ILIKE '%confidential%'"
    "    OR tag_name ILIKE '%gdpr%'"
    "    OR tag_name ILIKE '%classification%'"
    "    OR tag_value ILIKE '%pii%'"
    "    OR tag_value ILIKE '%sensitive%'"
    "    OR tag_value ILIKE '%confidential%'"
    "    OR tag_value ILIKE '%gdpr%'"
)

_TOTAL_COLUMNS_SQL = (
    "SELECT COUNT(*) AS total_columns"
    " FROM system.information_schema.columns"
    " WHERE table_catalog <> 'hive_metastore'"
)

_REF = "https://docs.databricks.com/en/data-governance/unity-catalog/tags.html"


@register(layer="storage", question_ids=["STO-DG-05"])
class SensitiveClassificationCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        coverage_rows = ctx.sql.query(_COLUMN_TAG_COVERAGE_SQL)
        sensitivity_rows = ctx.sql.query(_SENSITIVITY_TAGS_SQL)
        total_rows = ctx.sql.query(_TOTAL_COLUMNS_SQL)

        tagged_columns = int(
            (coverage_rows[0].get("tagged_columns") or 0) if coverage_rows else 0
        )
        tagged_tables = int(
            (coverage_rows[0].get("tagged_tables") or 0) if coverage_rows else 0
        )
        sensitivity_tag_count = int(
            (sensitivity_rows[0].get("sensitivity_tag_count") or 0) if sensitivity_rows else 0
        )
        sensitivity_tagged_tables = int(
            (sensitivity_rows[0].get("sensitivity_tagged_tables") or 0)
            if sensitivity_rows
            else 0
        )
        total_columns = int(
            (total_rows[0].get("total_columns") or 0) if total_rows else 0
        )

        pct = (
            round(100.0 * tagged_columns / total_columns, 1) if total_columns > 0 else 0.0
        )

        coverage_evidence = Evidence(
            kind="sql",
            summary=(
                f"{tagged_columns} columns tagged across {tagged_tables} tables"
                f" ({pct}% of {total_columns} total UC columns)"
            ),
            detail=_COLUMN_TAG_COVERAGE_SQL,
            rows=coverage_rows[:5] + total_rows[:3],
            ref=_REF,
        )
        sensitivity_evidence = Evidence(
            kind="sql",
            summary=(
                f"{sensitivity_tag_count} column tags indicate sensitivity "
                f"(pii/sensitive/confidential/gdpr/classification) across "
                f"{sensitivity_tagged_tables} tables; "
                "these are the primary signal for masking classification"
            ),
            detail=_SENSITIVITY_TAGS_SQL,
            rows=sensitivity_rows[:5],
            ref=_REF,
        )
        return [coverage_evidence, sensitivity_evidence]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
