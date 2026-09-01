"""Intermediate and processed data protection check (LLM-judged).

Answers:
  PRO-SCP-04  Protect intermediate/processed data

Signal: access governance posture for processed data from system.information_schema:
- Unity Catalog coverage: share of tables governed by UC (not in hive_metastore)
- Grant breadth: ratio of broad/public grants to total grants on UC tables

At-rest encryption is enforced at the cloud/workspace level and is NOT directly
visible via workspace system tables; a note records this limitation. The LLM judge
weighs the governance proxy signals.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_UC_COVERAGE_SQL = (
    "SELECT COUNT(*) AS total_tables, "
    "SUM(CASE WHEN table_catalog <> 'hive_metastore' THEN 1 ELSE 0 END) AS uc_tables "
    "FROM system.information_schema.tables "
    "WHERE table_type IN ('MANAGED','EXTERNAL')"
)

_GRANT_BREADTH_SQL = (
    "SELECT COUNT(*) AS total_grants, "
    "SUM(CASE WHEN grantee = 'account users' "
    "         OR grantee ILIKE '%PUBLIC%' THEN 1 ELSE 0 END) AS broad_grants "
    "FROM system.information_schema.table_privileges "
    "WHERE table_catalog <> 'hive_metastore'"
)

_NOTE = (
    "At-rest encryption for Databricks storage is enforced at the cloud/workspace level "
    "(cloud provider default or customer-managed keys) and is NOT visible via workspace "
    "system tables. This check assesses the access-governance proxy (UC coverage, grant "
    "breadth) as the observable signal; admin confirmation is required to verify the "
    "actual encryption posture for intermediate and processed data."
)

_REF = "https://docs.databricks.com/en/security/access-control/table-acls/index.html"


@register(layer="processing", question_ids=["PRO-SCP-04"])
class DataProtectionCheck(Check):
    """Assess protection of intermediate/processed data via governance proxy signals.

    Evidence:
    - UC coverage: share of tables governed by Unity Catalog (not in hive_metastore)
    - Grant breadth: ratio of broad/public grants to total grants on UC tables
    - Note: encryption at rest is not observable from system tables
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        uc_rows = ctx.sql.query(_UC_COVERAGE_SQL)
        grant_rows = ctx.sql.query(_GRANT_BREADTH_SQL)

        total_tables = int((uc_rows[0].get("total_tables") or 0) if uc_rows else 0)
        uc_tables = int((uc_rows[0].get("uc_tables") or 0) if uc_rows else 0)
        total_grants = int((grant_rows[0].get("total_grants") or 0) if grant_rows else 0)
        broad_grants = int((grant_rows[0].get("broad_grants") or 0) if grant_rows else 0)

        uc_pct = round(100.0 * uc_tables / total_tables, 1) if total_tables > 0 else 0.0
        broad_pct = (
            round(100.0 * broad_grants / total_grants, 1) if total_grants > 0 else 0.0
        )

        uc_evidence = Evidence(
            kind="sql",
            summary=(
                f"{uc_tables} of {total_tables} tables ({uc_pct}%) governed by Unity Catalog"
            ),
            detail=_UC_COVERAGE_SQL,
            rows=[{"total_tables": total_tables, "uc_tables": uc_tables, "uc_pct": uc_pct}],
            ref=_REF,
        )
        grant_evidence = Evidence(
            kind="sql",
            summary=(
                f"{total_grants} total table grant(s); {broad_grants} broad/public grant(s) "
                f"({broad_pct}%) — high broad_grants indicates over-permissive access"
            ),
            detail=_GRANT_BREADTH_SQL,
            rows=[{
                "total_grants": total_grants,
                "broad_grants": broad_grants,
                "broad_pct": broad_pct,
            }],
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )
        return [uc_evidence, grant_evidence, note_evidence]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
