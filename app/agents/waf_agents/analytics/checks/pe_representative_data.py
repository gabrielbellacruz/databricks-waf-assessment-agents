"""Production-representative analytics data check (LLM-judged).

Answers:
  ANA-PE-04  Test analytics on production-representative data

Analytics queries developed against a small or unrepresentative dataset may
produce misleading performance results when promoted to production. Testing
on production-representative data (or a sampled clone) ensures that query
plans, partition pruning, and data skipping behaviour match production.

Observable proxies:
  - ``system.information_schema.schemata`` / ``tables``: catalog/schema names
    can reveal dev/test/staging environments (e.g. schemas named ``dev_*``,
    ``test_*``, ``staging_*``). Their existence indicates some environment
    separation exists; whether those environments hold representative data
    volumes is not visible.
  - ``system.query.history``: presence of SELECT queries against tables in
    dev/test/staging schemas suggests developers query non-production
    environments. Row counts and table sizes are not exposed in query.history.

What is NOT observable: actual data volumes in dev/test environments, whether
sample ratios are documented, or whether performance benchmarks are tracked.
Manual confirmation is required for a definitive assessment.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SCHEMA_SQL = (
    "SELECT schema_name, catalog_name "
    "FROM system.information_schema.schemata "
    "WHERE catalog_name <> 'hive_metastore' "
    "ORDER BY catalog_name, schema_name "
    "LIMIT 100"
)

_DEV_QUERY_SQL = (
    "SELECT "
    "SUM(CASE WHEN statement_text ILIKE '%dev%' "
    "         OR statement_text ILIKE '%test%' "
    "         OR statement_text ILIKE '%staging%' "
    "THEN 1 ELSE 0 END) AS dev_env_queries, "
    "COUNT(*) AS total_queries "
    "FROM system.query.history "
    "WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS "
    "AND statement_type = 'SELECT'"
)

_NOTE = (
    "Testing analytics on production-representative data requires either a sampled "
    "clone of production tables or a staging environment loaded with realistic data "
    "volumes and distributions. Catalog/schema names containing 'dev', 'test', or "
    "'staging' indicate environment separation exists, but actual data volumes and "
    "representativeness cannot be determined from system tables. Manual review of "
    "environment data volumes and benchmarking practices is needed."
)

_REF = "https://docs.databricks.com/en/delta/clone.html"


@register(layer="analytics", question_ids=["ANA-PE-04"])
class RepresentativeDataCheck(Check):
    """Assess whether analytics development uses production-representative data.

    Evidence:
      1. Schema names across non-hive catalogs to identify dev/test environments.
      2. SELECT query patterns referencing dev/test/staging in query.history
         (last 30 days) as a proxy for environment separation.
      3. A note recording what cannot be determined from system tables.
    The LLM judge weighs all three pieces.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        schema_rows = ctx.sql.query(_SCHEMA_SQL)
        dev_query_rows = ctx.sql.query(_DEV_QUERY_SQL)

        dev_schemas = [
            r for r in schema_rows
            if any(
                kw in str(r.get("schema_name") or "").lower()
                for kw in ("dev", "test", "staging", "sandbox")
            )
        ]

        if schema_rows:
            schema_summary = (
                f"{len(schema_rows)} schema(s) found across non-hive catalogs; "
                f"{len(dev_schemas)} appear to be dev/test/staging environments "
                "(name contains dev/test/staging/sandbox)"
            )
        else:
            schema_summary = "No schemas found in system.information_schema.schemata"

        schema_evidence = Evidence(
            kind="sql",
            summary=schema_summary,
            detail=_SCHEMA_SQL,
            rows=[
                {"schema_name": r.get("schema_name"), "catalog_name": r.get("catalog_name")}
                for r in dev_schemas[:20]
            ],
            ref=_REF,
        )

        if dev_query_rows:
            row = dev_query_rows[0]
            dev_env_queries = int(row.get("dev_env_queries") or 0)
            total_queries = int(row.get("total_queries") or 0)
            pct = round(100.0 * dev_env_queries / total_queries, 1) if total_queries > 0 else 0.0
            dev_query_summary = (
                f"SELECT queries referencing dev/test/staging (last 30 days): "
                f"{dev_env_queries} of {total_queries} ({pct}%)"
            )
        else:
            dev_env_queries = 0
            total_queries = 0
            dev_query_summary = "No SELECT query history found for the last 30 days"

        dev_query_evidence = Evidence(
            kind="sql",
            summary=dev_query_summary,
            detail=_DEV_QUERY_SQL,
            rows=[{"dev_env_queries": dev_env_queries, "total_queries": total_queries}],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [schema_evidence, dev_query_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
