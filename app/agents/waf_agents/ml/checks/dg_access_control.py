"""Access control check for ML objects (LLM-judged).

Answers:
  ML-DG-03  Control access to models, features, and training data

Signals:
  * ``system.information_schema.table_privileges`` — grants on tables in
    ML-suggestive schemas (feature*, model*, ml*, train*) in Unity Catalog,
    split by group/service-principal grants (grantee without '@') vs individual
    user grants (grantee contains '@'). Group-based grants indicate centralized,
    least-privilege access; per-user grants suggest ad-hoc access.
  * ``system.information_schema.tables`` — count of ML-suggestive tables in
    Unity Catalog with and without any access grants, to detect ungoverned ML objects.
  * Note: MLflow Model Registry permissions (model-level ACLs in the legacy Workspace
    Model Registry or UC model alias permissions) are not exposed in table_privileges;
    this check measures table-level access only.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

# Grants on ML-related UC tables: split group vs user grants.
_ML_GRANTS_SQL = (
    "SELECT COUNT(*) AS total_ml_grants, "
    "SUM(CASE WHEN grantee LIKE '%@%' THEN 1 ELSE 0 END) AS user_grants, "
    "SUM(CASE WHEN grantee NOT LIKE '%@%' THEN 1 ELSE 0 END) AS group_grants "
    "FROM system.information_schema.table_privileges "
    "WHERE table_catalog <> 'hive_metastore' "
    "  AND (LOWER(table_schema) LIKE '%feature%' "
    "       OR LOWER(table_schema) LIKE '%model%' "
    "       OR LOWER(table_schema) LIKE '%ml%' "
    "       OR LOWER(table_schema) LIKE '%train%')"
)

# ML-suggestive UC tables: how many have any explicit grant.
_ML_TABLES_COVERAGE_SQL = (
    "SELECT COUNT(*) AS total_ml_uc_tables, "
    "SUM(CASE WHEN table_catalog || '.' || table_schema || '.' || table_name IN ("
    "  SELECT DISTINCT table_catalog || '.' || table_schema || '.' || table_name "
    "  FROM system.information_schema.table_privileges "
    "  WHERE table_catalog <> 'hive_metastore'"
    ") THEN 1 ELSE 0 END) AS ml_tables_with_grants "
    "FROM system.information_schema.tables "
    "WHERE table_catalog <> 'hive_metastore' "
    "  AND table_type IN ('MANAGED','EXTERNAL','MODEL') "
    "  AND (LOWER(table_schema) LIKE '%feature%' "
    "       OR LOWER(table_schema) LIKE '%model%' "
    "       OR LOWER(table_schema) LIKE '%ml%' "
    "       OR LOWER(table_schema) LIKE '%train%')"
)

_NOTE = (
    "This check covers table-level grants on UC tables in ML-suggestive schemas. "
    "MLflow Model Registry alias-level permissions and Unity Catalog model grants "
    "may not all surface in system.information_schema.table_privileges. "
    "Row/column-level security (masks, filters) on feature tables is not measured here."
)

_REF = (
    "https://docs.databricks.com/en/data-governance/unity-catalog/manage-privileges/index.html"
)


@register(layer="ml", question_ids=["ML-DG-03"])
class MlAccessControlCheck(Check):
    """LLM-judged check for ML-DG-03: access control on models, features, and training data."""

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        grant_rows = ctx.sql.query(_ML_GRANTS_SQL)
        coverage_rows = ctx.sql.query(_ML_TABLES_COVERAGE_SQL)

        grow = grant_rows[0] if grant_rows else {}
        total_ml_grants = int(grow.get("total_ml_grants") or 0)
        user_grants = int(grow.get("user_grants") or 0)
        group_grants = int(grow.get("group_grants") or 0)

        crow = coverage_rows[0] if coverage_rows else {}
        total_ml_tables = int(crow.get("total_ml_uc_tables") or 0)
        tables_with_grants = int(crow.get("ml_tables_with_grants") or 0)

        grant_evidence = Evidence(
            kind="sql",
            summary=(
                f"{total_ml_grants} grants on ML-suggestive UC tables: "
                f"{group_grants} to groups/service-principals, {user_grants} to individual users"
            ),
            detail=_ML_GRANTS_SQL,
            rows=[
                {
                    "total_ml_grants": total_ml_grants,
                    "user_grants": user_grants,
                    "group_grants": group_grants,
                }
            ],
            ref=_REF,
        )
        coverage_evidence = Evidence(
            kind="sql",
            summary=(
                f"{tables_with_grants} of {total_ml_tables} ML-suggestive UC tables "
                "have at least one explicit access grant"
            ),
            detail=_ML_TABLES_COVERAGE_SQL,
            rows=[
                {
                    "total_ml_uc_tables": total_ml_tables,
                    "ml_tables_with_grants": tables_with_grants,
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
        return [grant_evidence, coverage_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
