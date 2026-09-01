"""Centralized access control check (LLM-judged).

Answers:
  STO-DG-03  Centralize access control on stored data

Signal: ``system.information_schema.table_privileges`` — total grants, distinct
grantees, count of broad/public grants (grantee = 'account users' or grantee
ILIKE '%PUBLIC%'), and the share of UC-governed tables with any explicit grant.
The LLM judge weighs whether access is centrally controlled with least privilege.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_GRANT_SUMMARY_SQL = (
    "SELECT COUNT(*) AS total_grants,"
    " COUNT(DISTINCT grantee) AS distinct_grantees,"
    " SUM(CASE WHEN grantee = 'account users'"
    "          OR grantee ILIKE '%PUBLIC%' THEN 1 ELSE 0 END) AS broad_grants"
    " FROM system.information_schema.table_privileges"
    " WHERE table_catalog <> 'hive_metastore'"
)

_UC_TABLE_COUNT_SQL = (
    "SELECT COUNT(*) AS uc_table_count"
    " FROM system.information_schema.tables"
    " WHERE table_type IN ('MANAGED', 'EXTERNAL')"
    " AND table_catalog <> 'hive_metastore'"
)

_TOP_GRANTEES_SQL = (
    "SELECT grantee, COUNT(*) AS grant_count"
    " FROM system.information_schema.table_privileges"
    " WHERE table_catalog <> 'hive_metastore'"
    " GROUP BY grantee"
    " ORDER BY grant_count DESC"
    " LIMIT 20"
)

_REF = (
    "https://docs.databricks.com/en/data-governance/unity-catalog/"
    "manage-privileges/privileges.html"
)


@register(layer="storage", question_ids=["STO-DG-03"])
class CentralizedAccessControlCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        grant_rows = ctx.sql.query(_GRANT_SUMMARY_SQL)
        uc_rows = ctx.sql.query(_UC_TABLE_COUNT_SQL)
        grantee_rows = ctx.sql.query(_TOP_GRANTEES_SQL)

        total_grants = int(
            (grant_rows[0].get("total_grants") or 0) if grant_rows else 0
        )
        distinct_grantees = int(
            (grant_rows[0].get("distinct_grantees") or 0) if grant_rows else 0
        )
        broad_grants = int(
            (grant_rows[0].get("broad_grants") or 0) if grant_rows else 0
        )
        uc_table_count = int(
            (uc_rows[0].get("uc_table_count") or 0) if uc_rows else 0
        )

        broad_pct = (
            round(100.0 * broad_grants / total_grants, 1) if total_grants > 0 else 0.0
        )

        grant_evidence = Evidence(
            kind="sql",
            summary=(
                f"{total_grants} total table grants across {distinct_grantees} distinct "
                f"grantees; {broad_grants} broad/public grants ({broad_pct}% of total)"
            ),
            detail=_GRANT_SUMMARY_SQL,
            rows=(grant_rows[:5] + uc_rows[:3]),
            ref=_REF,
        )
        table_coverage_evidence = Evidence(
            kind="sql",
            summary=(
                f"{uc_table_count} managed/external tables in Unity Catalog (excluding "
                f"hive_metastore); UC governance is the prerequisite for centralized ACLs"
            ),
            detail=_UC_TABLE_COUNT_SQL,
            rows=uc_rows[:3],
            ref=_REF,
        )
        grantee_evidence = Evidence(
            kind="sql",
            summary=(
                "Top grantees by grant count (up to 20); "
                "broad grantees like 'account users' indicate wide-open access"
            ),
            detail=_TOP_GRANTEES_SQL,
            rows=grantee_rows[:20],
            ref=_REF,
        )
        return [grant_evidence, table_coverage_evidence, grantee_evidence]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
