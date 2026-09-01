"""Feature store usage check (LLM-judged).

Answers:
  ML-PE-03  Use the feature store to avoid recomputing features

Databricks Feature Engineering (formerly Feature Store) stores precomputed
features as Unity Catalog tables with feature-store metadata. These tables
are identifiable in ``system.information_schema.tables`` by schema or table
names containing 'feature' as a naming convention, or more precisely via
table properties. The agent checks for any schemas/tables whose names
suggest feature-store usage as a proxy. A strong limitation note accompanies
the evidence because naming conventions are not enforced and many feature
tables may be named differently.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

# Distinct needle: "feature_schemas"
_SCHEMA_SQL = """\
SELECT
  COUNT(*) AS feature_schemas
FROM system.information_schema.schemata
WHERE schema_name ILIKE '%feature%'
  AND catalog_name NOT IN ('hive_metastore', '__databricks_internal')\
"""

# Distinct needle: "feature_tables"
_TABLE_SQL = """\
SELECT
  COUNT(*) AS feature_tables,
  COUNT(DISTINCT table_schema) AS schemas_with_features
FROM system.information_schema.tables
WHERE (
  table_schema ILIKE '%feature%'
  OR table_name ILIKE '%feature%'
  OR table_name ILIKE '%feat_%'
)
AND table_catalog NOT IN ('hive_metastore', '__databricks_internal')\
"""

_NOTE = (
    "Feature store table detection relies on schema/table naming conventions — "
    "not every feature table will be named with 'feature'. The Databricks Feature "
    "Engineering API registers tables with special metadata that is not directly "
    "queryable via system.information_schema by the agent's service principal. "
    "Manual review of Feature Engineering API usage and feature table definitions is "
    "required to confirm feature store adoption."
)

_REF = "https://docs.databricks.com/en/machine-learning/feature-store/index.html"


@register(layer="ml", question_ids=["ML-PE-03"])
class MlFeatureStoreCheck(Check):
    """Assess feature store adoption via schema/table naming heuristics.

    Evidence is gathered from system.information_schema.schemata and tables:
    count of schemas and tables whose names suggest feature-store usage.
    A note evidence records that naming conventions are not enforced and
    Feature Engineering API metadata is not directly observable.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        evidence: list[Evidence] = []

        # 1. Feature-named schemas
        schema_rows = ctx.sql.query(_SCHEMA_SQL)
        if schema_rows:
            feature_schemas = int(schema_rows[0].get("feature_schemas") or 0)
            schema_summary = (
                f"{feature_schemas} schema(s) with 'feature' in the name found in Unity Catalog"
            )
        else:
            feature_schemas = 0
            schema_summary = (
                "No schemas found with 'feature' in the name (or information_schema not accessible)"
            )

        evidence.append(
            Evidence(
                kind="sql",
                summary=schema_summary,
                detail=_SCHEMA_SQL,
                rows=[{"feature_schemas": feature_schemas}],
                ref="https://docs.databricks.com/en/data-governance/unity-catalog/index.html",
            )
        )

        # 2. Feature-named tables
        table_rows = ctx.sql.query(_TABLE_SQL)
        if table_rows:
            row = table_rows[0]
            feature_tables = int(row.get("feature_tables") or 0)
            schemas_with_features = int(row.get("schemas_with_features") or 0)
            table_summary = (
                f"{feature_tables} table(s) with 'feature' in the name across "
                f"{schemas_with_features} schema(s) in Unity Catalog"
            )
        else:
            feature_tables = schemas_with_features = 0
            table_summary = (
                "No tables found with 'feature' in the name (or information_schema not accessible)"
            )

        evidence.append(
            Evidence(
                kind="sql",
                summary=table_summary,
                detail=_TABLE_SQL,
                rows=[
                    {
                        "feature_tables": feature_tables,
                        "schemas_with_features": schemas_with_features,
                    }
                ],
                ref=_REF,
            )
        )

        evidence.append(
            Evidence(
                kind="note",
                summary=_NOTE,
                rows=[],
                ref=_REF,
            )
        )

        return evidence

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
