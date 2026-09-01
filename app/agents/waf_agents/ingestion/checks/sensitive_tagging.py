"""Sensitive data tagging check (LLM-judged).

Answers:
  ING-DG-03  Classify and tag sensitive data as it is ingested

Signal: column-level tag coverage in Unity Catalog, from
``system.information_schema.column_tags`` vs. the total column count in
``system.information_schema.columns``. Catalog-level tags from
``system.information_schema.catalog_tags`` provide a complementary governance
signal. The raw counts are handed to the LLM judge, which weighs coverage
breadth and decides whether the practice is met / partial / not_met / unknown.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_COLUMN_TAGS_SQL = (
    "SELECT COUNT(*) AS tagged_columns,"
    " COUNT(DISTINCT catalog_name||'.'||schema_name||'.'||table_name) AS tagged_tables"
    " FROM system.information_schema.column_tags"
)

_TOTAL_COLUMNS_SQL = (
    "SELECT COUNT(*) AS total_columns"
    " FROM system.information_schema.columns"
    " WHERE table_catalog <> 'hive_metastore'"
)

_CATALOG_TAGS_SQL = (
    "SELECT COUNT(*) AS catalog_tags"
    " FROM system.information_schema.catalog_tags"
)

_REF = "https://docs.databricks.com/en/data-governance/unity-catalog/tags.html"


@register(layer="ingestion", question_ids=["ING-DG-03"])
class SensitiveTaggingCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        tag_rows = ctx.sql.query(_COLUMN_TAGS_SQL)
        total_rows = ctx.sql.query(_TOTAL_COLUMNS_SQL)
        catalog_rows = ctx.sql.query(_CATALOG_TAGS_SQL)

        tagged_cols = int((tag_rows[0].get("tagged_columns") or 0) if tag_rows else 0)
        tagged_tables = int((tag_rows[0].get("tagged_tables") or 0) if tag_rows else 0)
        total_cols = int((total_rows[0].get("total_columns") or 0) if total_rows else 0)
        catalog_tags = int((catalog_rows[0].get("catalog_tags") or 0) if catalog_rows else 0)

        pct = round(100.0 * tagged_cols / total_cols, 1) if total_cols > 0 else 0.0

        column_evidence = Evidence(
            kind="sql",
            summary=(
                f"{tagged_cols} columns tagged across {tagged_tables} tables"
                f" ({pct}% of {total_cols} total UC columns)"
            ),
            detail=_COLUMN_TAGS_SQL,
            rows=(tag_rows[:25] + total_rows[:5]),
            ref=_REF,
        )
        catalog_evidence = Evidence(
            kind="sql",
            summary=f"{catalog_tags} catalog-level tags applied",
            detail=_CATALOG_TAGS_SQL,
            rows=catalog_rows[:5],
            ref=_REF,
        )
        return [column_evidence, catalog_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
