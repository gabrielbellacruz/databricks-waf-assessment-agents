"""Environment isolation check for processing workloads (LLM-judged).

Answers:
  PRO-OE-04  Isolate dev, staging, and production for processing

Signal: schema and catalog naming conventions indicating environment separation
from system.information_schema.schemata and .catalogs. Well-architected workspaces
separate dev/test/staging/prod environments, often reflected in catalog or schema
names. A note records that workspace-level isolation would not appear here.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_DEV_PATTERN = "dev|develop|local|sandbox"
_STAGING_PATTERN = "staging|stg|uat|test|qa|preprod|pre_prod"
_PROD_PATTERN = "prod|production|prd|live"

_SQL_SCHEMAS = (
    "SELECT COUNT(*) AS total_schemas, "
    f"SUM(CASE WHEN LOWER(schema_name) RLIKE '{_DEV_PATTERN}' THEN 1 ELSE 0 END) "
    "AS dev_schemas, "
    f"SUM(CASE WHEN LOWER(schema_name) RLIKE '{_STAGING_PATTERN}' THEN 1 ELSE 0 END) "
    "AS staging_schemas, "
    f"SUM(CASE WHEN LOWER(schema_name) RLIKE '{_PROD_PATTERN}' THEN 1 ELSE 0 END) "
    "AS prod_schemas "
    "FROM system.information_schema.schemata "
    "WHERE schema_name <> 'information_schema' "
    "AND catalog_name <> 'hive_metastore'"
)

_SQL_CATALOGS = (
    "SELECT COUNT(*) AS total_catalogs, "
    f"SUM(CASE WHEN LOWER(catalog_name) RLIKE '{_DEV_PATTERN}' THEN 1 ELSE 0 END) "
    "AS dev_catalogs, "
    f"SUM(CASE WHEN LOWER(catalog_name) RLIKE '{_STAGING_PATTERN}' THEN 1 ELSE 0 END) "
    "AS staging_catalogs, "
    f"SUM(CASE WHEN LOWER(catalog_name) RLIKE '{_PROD_PATTERN}' THEN 1 ELSE 0 END) "
    "AS prod_catalogs "
    "FROM system.information_schema.catalogs "
    "WHERE catalog_name <> 'hive_metastore'"
)

_NOTE = (
    "Environment isolation is only partially observable from catalog/schema names. A workspace "
    "may enforce isolation through separate Databricks workspaces (dev/staging/prod workspaces) "
    "rather than catalog/schema naming, which would not appear in this scan. Manual confirmation "
    "is needed to determine whether environment separation is enforced via separate workspaces, "
    "catalogs, or schemas."
)

_REF = "https://docs.databricks.com/en/dev-tools/bundles/deployment-targets.html"


@register(layer="processing", question_ids=["PRO-OE-04"])
class EnvIsolationCheck(Check):
    """Assess dev/staging/prod isolation by schema and catalog naming patterns.

    Both schema-level and catalog-level environment naming conventions are
    gathered as signals. A note records that workspace-level isolation is not
    visible here and requires manual confirmation.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        schema_rows = ctx.sql.query(_SQL_SCHEMAS)
        catalog_rows = ctx.sql.query(_SQL_CATALOGS)

        schema_row = schema_rows[0] if schema_rows else {}
        catalog_row = catalog_rows[0] if catalog_rows else {}

        total_schemas = int(schema_row.get("total_schemas") or 0)
        dev_schemas = int(schema_row.get("dev_schemas") or 0)
        staging_schemas = int(schema_row.get("staging_schemas") or 0)
        prod_schemas = int(schema_row.get("prod_schemas") or 0)

        total_catalogs = int(catalog_row.get("total_catalogs") or 0)
        dev_catalogs = int(catalog_row.get("dev_catalogs") or 0)
        staging_catalogs = int(catalog_row.get("staging_catalogs") or 0)
        prod_catalogs = int(catalog_row.get("prod_catalogs") or 0)

        env_schemas = dev_schemas + staging_schemas + prod_schemas
        env_catalogs = dev_catalogs + staging_catalogs + prod_catalogs

        schema_evidence = Evidence(
            kind="sql",
            summary=(
                f"{env_schemas} of {total_schemas} schema(s) match env-separation naming "
                f"(dev: {dev_schemas}, staging: {staging_schemas}, prod: {prod_schemas})"
            ),
            detail=_SQL_SCHEMAS,
            rows=[{
                "total_schemas": total_schemas,
                "dev_schemas": dev_schemas,
                "staging_schemas": staging_schemas,
                "prod_schemas": prod_schemas,
            }],
            ref=_REF,
        )
        catalog_evidence = Evidence(
            kind="sql",
            summary=(
                f"{env_catalogs} of {total_catalogs} catalog(s) match env-separation naming "
                f"(dev: {dev_catalogs}, staging: {staging_catalogs}, prod: {prod_catalogs})"
            ),
            detail=_SQL_CATALOGS,
            rows=[{
                "total_catalogs": total_catalogs,
                "dev_catalogs": dev_catalogs,
                "staging_catalogs": staging_catalogs,
                "prod_catalogs": prod_catalogs,
            }],
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )
        return [schema_evidence, catalog_evidence, note_evidence]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
