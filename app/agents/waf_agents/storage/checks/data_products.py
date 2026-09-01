"""Curated data products check (LLM-judged).

Answers:
  STO-IU-03  Publish curated stored data as reusable data products

Signals:
  * Share of managed/external tables that carry a non-empty description/comment
    (``system.information_schema.tables``).
  * Tables living in schemas whose names match curated/gold/serving/mart patterns
    (``system.information_schema.tables``).
  * Tables tagged with curation markers (certified, product, gold, data_product)
    from ``system.information_schema.table_tags``.

The LLM judge weighs these signals to decide whether curated data products exist
vs raw dumps with no curation signal.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_DESCRIBED_TABLES_SQL = (
    "SELECT COUNT(*) AS total_tables,"
    " SUM(CASE WHEN comment IS NOT NULL AND trim(comment) <> '' THEN 1 ELSE 0 END)"
    " AS described_tables"
    " FROM system.information_schema.tables"
    " WHERE table_catalog <> 'hive_metastore'"
    " AND table_type IN ('MANAGED', 'EXTERNAL')"
)

_CURATED_SCHEMAS_SQL = (
    "SELECT COUNT(DISTINCT table_catalog || '.' || table_schema) AS curated_schemas,"
    " COUNT(*) AS curated_tables"
    " FROM system.information_schema.tables"
    " WHERE table_catalog <> 'hive_metastore'"
    " AND (LOWER(table_schema) LIKE '%gold%'"
    "   OR LOWER(table_schema) LIKE '%serving%'"
    "   OR LOWER(table_schema) LIKE '%mart%'"
    "   OR LOWER(table_schema) LIKE '%curated%')"
)

_CERTIFIED_TAGS_SQL = (
    "SELECT COUNT(DISTINCT catalog_name || '.' || schema_name || '.' || table_name)"
    " AS certified_tables"
    " FROM system.information_schema.table_tags"
    " WHERE LOWER(tag_name) IN ('certified', 'product', 'gold', 'data_product')"
    "   OR LOWER(tag_value) IN ('certified', 'gold', 'true')"
)

_REF = "https://docs.databricks.com/en/data-governance/unity-catalog/best-practices.html"


@register(layer="storage", question_ids=["STO-IU-03"])
class DataProductsCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        desc_rows = ctx.sql.query(_DESCRIBED_TABLES_SQL)
        curated_rows = ctx.sql.query(_CURATED_SCHEMAS_SQL)
        tag_rows = ctx.sql.query(_CERTIFIED_TAGS_SQL)

        desc_row = desc_rows[0] if desc_rows else {}
        total_tables = int(desc_row.get("total_tables") or 0)
        described_tables = int(desc_row.get("described_tables") or 0)
        pct = round(100.0 * described_tables / total_tables, 1) if total_tables > 0 else 0.0

        curated_row = curated_rows[0] if curated_rows else {}
        curated_schemas = int(curated_row.get("curated_schemas") or 0)
        curated_tables = int(curated_row.get("curated_tables") or 0)

        tag_row = tag_rows[0] if tag_rows else {}
        certified_tables = int(tag_row.get("certified_tables") or 0)

        description_evidence = Evidence(
            kind="sql",
            summary=(
                f"{described_tables} of {total_tables} managed/external tables"
                f" have a non-empty description ({pct}%)"
            ),
            detail=_DESCRIBED_TABLES_SQL,
            rows=desc_rows[:5],
            ref=_REF,
        )
        curated_evidence = Evidence(
            kind="sql",
            summary=(
                f"{curated_tables} table(s) in {curated_schemas}"
                " curated/gold/serving/mart schema(s)"
            ),
            detail=_CURATED_SCHEMAS_SQL,
            rows=curated_rows[:5],
            ref=_REF,
        )
        tag_evidence = Evidence(
            kind="sql",
            summary=f"{certified_tables} table(s) tagged as certified/product/gold/data_product",
            detail=_CERTIFIED_TAGS_SQL,
            rows=tag_rows[:5],
            ref=_REF,
        )
        return [description_evidence, curated_evidence, tag_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
