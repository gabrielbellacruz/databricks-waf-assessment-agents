"""Model documentation and cards check (LLM-judged).

Answers:
  ML-DG-05  Maintain model documentation and cards

Signals:
  * ``system.information_schema.tables`` — count of tables in ML-suggestive schemas
    that have a non-empty comment, as a proxy for documentation of feature tables.
  * ``system.information_schema.table_tags`` — count of tables in ML-suggestive schemas
    that carry at least one tag; tags can encode model metadata such as owner, version,
    or quality tier.
  * Note: MLflow model cards (Markdown descriptions stored in MLflow Model Registry
    model versions or aliases) are NOT exposed in system.information_schema. UC Catalog
    and Schema comments are not checked here. This check can only measure table-level
    documentation signals — a workspace with thorough MLflow model cards will appear
    undocumented.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

# ML-suggestive UC tables: total vs those with non-empty comments.
_ML_COMMENTS_SQL = (
    "SELECT COUNT(*) AS total_ml_uc_tables, "
    "SUM(CASE WHEN comment IS NOT NULL AND comment <> '' THEN 1 ELSE 0 END) "
    "  AS tables_with_comments "
    "FROM system.information_schema.tables "
    "WHERE table_catalog <> 'hive_metastore' "
    "  AND table_type IN ('MANAGED','EXTERNAL','MODEL') "
    "  AND (LOWER(table_schema) LIKE '%feature%' "
    "       OR LOWER(table_schema) LIKE '%model%' "
    "       OR LOWER(table_schema) LIKE '%ml%' "
    "       OR LOWER(table_schema) LIKE '%train%')"
)

# ML-suggestive tables with at least one table-level tag.
_ML_TAGS_SQL = (
    "SELECT COUNT(DISTINCT catalog_name || '.' || schema_name || '.' || table_name) "
    "  AS tables_with_tags "
    "FROM system.information_schema.table_tags "
    "WHERE (LOWER(schema_name) LIKE '%feature%' "
    "       OR LOWER(schema_name) LIKE '%model%' "
    "       OR LOWER(schema_name) LIKE '%ml%' "
    "       OR LOWER(schema_name) LIKE '%train%')"
)

_NOTE = (
    "MLflow model cards (Markdown descriptions in MLflow Model Registry model versions "
    "or aliases) are NOT visible in system.information_schema. This check measures "
    "table-level comments and tags on UC tables in ML-suggestive schemas as a partial proxy. "
    "A workspace that documents models exclusively via MLflow will appear under-documented here."
)

_REF = "https://docs.databricks.com/en/machine-learning/manage-model-lifecycle/index.html"


@register(layer="ml", question_ids=["ML-DG-05"])
class MlModelDocumentationCheck(Check):
    """LLM-judged check for ML-DG-05: model documentation and cards."""

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        comment_rows = ctx.sql.query(_ML_COMMENTS_SQL)
        tag_rows = ctx.sql.query(_ML_TAGS_SQL)

        crow = comment_rows[0] if comment_rows else {}
        total_ml_tables = int(crow.get("total_ml_uc_tables") or 0)
        tables_with_comments = int(crow.get("tables_with_comments") or 0)

        trow = tag_rows[0] if tag_rows else {}
        tables_with_tags = int(trow.get("tables_with_tags") or 0)

        comment_evidence = Evidence(
            kind="sql",
            summary=(
                f"{tables_with_comments} of {total_ml_tables} ML-suggestive UC tables "
                "have a non-empty comment (table description)"
            ),
            detail=_ML_COMMENTS_SQL,
            rows=[
                {
                    "total_ml_uc_tables": total_ml_tables,
                    "tables_with_comments": tables_with_comments,
                }
            ],
            ref=_REF,
        )
        tag_evidence = Evidence(
            kind="sql",
            summary=(
                f"{tables_with_tags} ML-suggestive UC tables carry at least one table-level tag"
            ),
            detail=_ML_TAGS_SQL,
            rows=[{"tables_with_tags": tables_with_tags}],
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )
        return [comment_evidence, tag_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
