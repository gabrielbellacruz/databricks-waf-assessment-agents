"""Semantic layer consistency check (LLM-judged).

Answers:
  ANA-DG-02  Ensure a consistent semantic layer for metrics

Signals:
  * Count of views and materialized views in Unity Catalog (excluding hive_metastore)
    from ``system.information_schema.tables`` — views are the primary mechanism for
    a reusable semantic / metrics layer in Databricks SQL.
  * Views or tables whose schema or name matches metric/semantic/reporting/kpi/dim/fact
    naming conventions, indicating an intentional semantic layer.

The LLM judge decides whether the workspace has an organized, consistent semantic
layer vs ad-hoc view sprawl or no views at all.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_VIEWS_SQL = (
    "SELECT COUNT(*) AS total_views,"
    " SUM(CASE WHEN table_type = 'MATERIALIZED_VIEW' THEN 1 ELSE 0 END) AS materialized_views,"
    " SUM(CASE WHEN table_type = 'VIEW' THEN 1 ELSE 0 END) AS regular_views"
    " FROM system.information_schema.tables"
    " WHERE table_catalog <> 'hive_metastore'"
    " AND table_type IN ('VIEW','MATERIALIZED_VIEW')"
)

_SEMANTIC_NAMING_SQL = (
    "SELECT COUNT(DISTINCT table_catalog || '.' || table_schema) AS semantic_schemas,"
    " COUNT(*) AS semantic_objects"
    " FROM system.information_schema.tables"
    " WHERE table_catalog <> 'hive_metastore'"
    " AND (LOWER(table_schema) LIKE '%metric%'"
    "   OR LOWER(table_schema) LIKE '%semantic%'"
    "   OR LOWER(table_schema) LIKE '%reporting%'"
    "   OR LOWER(table_name) LIKE '%metric%'"
    "   OR LOWER(table_name) LIKE 'dim_%'"
    "   OR LOWER(table_name) LIKE 'fact_%'"
    "   OR LOWER(table_name) LIKE '%kpi%')"
)

_REF = (
    "https://docs.databricks.com/en/sql/user/materialized-views.html"
)


@register(layer="analytics", question_ids=["ANA-DG-02"])
class SemanticLayerCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        view_rows = ctx.sql.query(_VIEWS_SQL)
        naming_rows = ctx.sql.query(_SEMANTIC_NAMING_SQL)

        vrow = view_rows[0] if view_rows else {}
        total_views = int(vrow.get("total_views") or 0)
        materialized_views = int(vrow.get("materialized_views") or 0)
        regular_views = int(vrow.get("regular_views") or 0)

        nrow = naming_rows[0] if naming_rows else {}
        semantic_schemas = int(nrow.get("semantic_schemas") or 0)
        semantic_objects = int(nrow.get("semantic_objects") or 0)

        view_evidence = Evidence(
            kind="sql",
            summary=(
                f"{total_views} views/materialized views in UC"
                f" ({materialized_views} materialized, {regular_views} regular)"
            ),
            detail=_VIEWS_SQL,
            rows=view_rows[:5],
            ref=_REF,
        )
        naming_evidence = Evidence(
            kind="sql",
            summary=(
                f"{semantic_objects} objects in {semantic_schemas} schema(s) with"
                " metric/semantic/reporting/dim/fact/kpi naming conventions"
            ),
            detail=_SEMANTIC_NAMING_SQL,
            rows=naming_rows[:5],
            ref=_REF,
        )
        return [view_evidence, naming_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
