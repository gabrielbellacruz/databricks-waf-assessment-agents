"""Namespace strategy check (LLM-judged).

Answers:
  STO-DG-01  Organize storage with a Unity Catalog namespace strategy

Signal: number of catalogs, schemas per catalog, table counts per catalog/schema,
and the share of tables still in hive_metastore — all from
``system.information_schema``.  The LLM judge decides whether the distribution
suggests a coherent, governed namespace vs ad-hoc placement.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_CATALOG_COUNT_SQL = (
    "SELECT COUNT(*) AS catalog_count"
    " FROM system.information_schema.catalogs"
    " WHERE catalog_name <> 'hive_metastore'"
)

_SCHEMAS_PER_CATALOG_SQL = (
    "SELECT catalog_name, COUNT(*) AS schema_count"
    " FROM system.information_schema.schemata"
    " WHERE catalog_name <> 'hive_metastore'"
    " GROUP BY catalog_name"
    " ORDER BY schema_count DESC"
    " LIMIT 25"
)

_TABLES_PER_CATALOG_SQL = (
    "SELECT table_catalog, COUNT(*) AS table_count"
    " FROM system.information_schema.tables"
    " WHERE table_type IN ('MANAGED', 'EXTERNAL')"
    " GROUP BY table_catalog"
    " ORDER BY table_count DESC"
    " LIMIT 25"
)

_REF = "https://docs.databricks.com/en/data-governance/unity-catalog/best-practices.html"


@register(layer="storage", question_ids=["STO-DG-01"])
class NamespaceStrategyCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        catalog_rows = ctx.sql.query(_CATALOG_COUNT_SQL)
        schema_rows = ctx.sql.query(_SCHEMAS_PER_CATALOG_SQL)
        table_rows = ctx.sql.query(_TABLES_PER_CATALOG_SQL)

        catalog_count = int(
            (catalog_rows[0].get("catalog_count") or 0) if catalog_rows else 0
        )

        # Identify tables still in hive_metastore vs UC
        hive_count = 0
        uc_count = 0
        for r in table_rows:
            tc = str(r.get("table_catalog") or "")
            n = int(r.get("table_count") or 0)
            if tc == "hive_metastore":
                hive_count += n
            else:
                uc_count += n
        total_tables = hive_count + uc_count
        hive_pct = round(100.0 * hive_count / total_tables, 1) if total_tables > 0 else 0.0

        catalog_evidence = Evidence(
            kind="sql",
            summary=(
                f"{catalog_count} Unity Catalog catalogs found (excluding hive_metastore)"
            ),
            detail=_CATALOG_COUNT_SQL,
            rows=catalog_rows[:5],
            ref=_REF,
        )
        schema_evidence = Evidence(
            kind="sql",
            summary=(
                f"Schema distribution across catalogs: "
                f"{len(schema_rows)} catalog(s) have at least one schema"
            ),
            detail=_SCHEMAS_PER_CATALOG_SQL,
            rows=schema_rows[:25],
            ref=_REF,
        )
        table_evidence = Evidence(
            kind="sql",
            summary=(
                f"{uc_count} tables in UC catalogs, {hive_count} tables still in "
                f"hive_metastore ({hive_pct}% of {total_tables} total)"
            ),
            detail=_TABLES_PER_CATALOG_SQL,
            rows=table_rows[:25],
            ref=_REF,
        )
        return [catalog_evidence, schema_evidence, table_evidence]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
