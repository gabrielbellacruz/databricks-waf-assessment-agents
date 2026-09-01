"""Retention and lifecycle policy check (LLM-judged).

Answers:
  STO-DG-04  Define retention and lifecycle policies for stored data

Signal: retention-oriented tags on tables and schemas from
``system.information_schema.table_tags`` / ``schema_tags`` (tag_name ILIKE
'%retention%', '%lifecycle%', '%ttl%', '%expire%'), compared with total table
count.

Note: Delta table property-level retention settings (delta.deletedFileRetentionDuration,
delta.logRetentionDuration) are NOT visible in information_schema.  When those
are the primary retention mechanism, this check will report weak/sparse signal and
the LLM judge will likely return 'partial' or 'unknown'.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_RETENTION_TABLE_TAGS_SQL = (
    "SELECT COUNT(DISTINCT catalog_name||'.'||schema_name||'.'||table_name)"
    "   AS tagged_tables,"
    " COUNT(*) AS retention_tag_count"
    " FROM system.information_schema.table_tags"
    " WHERE tag_name ILIKE '%retention%'"
    "    OR tag_name ILIKE '%lifecycle%'"
    "    OR tag_name ILIKE '%ttl%'"
    "    OR tag_name ILIKE '%expire%'"
)

_RETENTION_SCHEMA_TAGS_SQL = (
    "SELECT COUNT(DISTINCT catalog_name||'.'||schema_name)"
    "   AS tagged_schemas,"
    " COUNT(*) AS retention_schema_tag_count"
    " FROM system.information_schema.schema_tags"
    " WHERE tag_name ILIKE '%retention%'"
    "    OR tag_name ILIKE '%lifecycle%'"
    "    OR tag_name ILIKE '%ttl%'"
    "    OR tag_name ILIKE '%expire%'"
)

_TOTAL_TABLES_SQL = (
    "SELECT COUNT(*) AS total_tables"
    " FROM system.information_schema.tables"
    " WHERE table_type IN ('MANAGED', 'EXTERNAL')"
    " AND table_catalog <> 'hive_metastore'"
)

_REF = (
    "https://docs.databricks.com/en/delta/data-retention.html"
)


@register(layer="storage", question_ids=["STO-DG-04"])
class RetentionPoliciesCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        table_tag_rows = ctx.sql.query(_RETENTION_TABLE_TAGS_SQL)
        schema_tag_rows = ctx.sql.query(_RETENTION_SCHEMA_TAGS_SQL)
        total_rows = ctx.sql.query(_TOTAL_TABLES_SQL)

        tagged_tables = int(
            (table_tag_rows[0].get("tagged_tables") or 0) if table_tag_rows else 0
        )
        retention_tag_count = int(
            (table_tag_rows[0].get("retention_tag_count") or 0) if table_tag_rows else 0
        )
        tagged_schemas = int(
            (schema_tag_rows[0].get("tagged_schemas") or 0) if schema_tag_rows else 0
        )
        total_tables = int(
            (total_rows[0].get("total_tables") or 0) if total_rows else 0
        )

        tag_pct = (
            round(100.0 * tagged_tables / total_tables, 1) if total_tables > 0 else 0.0
        )

        table_tag_evidence = Evidence(
            kind="sql",
            summary=(
                f"{tagged_tables} tables carry a retention/lifecycle/ttl/expire tag "
                f"({tag_pct}% of {total_tables} UC tables); "
                f"{retention_tag_count} individual retention tag entries"
            ),
            detail=_RETENTION_TABLE_TAGS_SQL,
            rows=table_tag_rows[:5] + total_rows[:3],
            ref=_REF,
        )
        schema_tag_evidence = Evidence(
            kind="sql",
            summary=(
                f"{tagged_schemas} schemas carry a retention/lifecycle/ttl/expire tag; "
                "schema-level tags can indicate org-wide retention governance"
            ),
            detail=_RETENTION_SCHEMA_TAGS_SQL,
            rows=schema_tag_rows[:5],
            ref=_REF,
        )
        delta_note_evidence = Evidence(
            kind="sql",
            summary=(
                "NOTE: Delta property-level retention (delta.deletedFileRetentionDuration, "
                "delta.logRetentionDuration) is NOT visible in information_schema. "
                "If the workspace uses only Delta properties for retention, "
                "tag-based signal will be sparse and this check will return partial/unknown."
            ),
            detail="",
            rows=[],
            ref=_REF,
        )
        return [table_tag_evidence, schema_tag_evidence, delta_note_evidence]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
