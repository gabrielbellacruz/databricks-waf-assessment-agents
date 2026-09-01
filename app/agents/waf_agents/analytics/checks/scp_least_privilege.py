"""Least-privilege check for analytics data access (LLM-judged).

Answers:
  ANA-SCP-02  Enforce least privilege on analytics data

Signal: whether table grants in Unity Catalog go to groups / service-principals
(centralized, least-privilege) vs individual users (ad-hoc, harder to revoke).
Grantees containing '@' are classified as individual users; all others (groups,
service principals, built-in roles such as 'account users') are treated as
centralized principals.
Source: system.information_schema.table_privileges (Unity Catalog only;
hive_metastore is excluded). The LLM judge weighs the ratio and returns a verdict.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = (
    "SELECT COUNT(*) AS total_grants, "
    "SUM(CASE WHEN grantee LIKE '%@%' THEN 1 ELSE 0 END) AS user_grants, "
    "SUM(CASE WHEN grantee NOT LIKE '%@%' THEN 1 ELSE 0 END) AS group_grants "
    "FROM system.information_schema.table_privileges "
    "WHERE table_catalog <> 'hive_metastore'"
)

_REF = (
    "https://docs.databricks.com/en/data-governance/unity-catalog/manage-privileges/index.html"
)


@register(layer="analytics", question_ids=["ANA-SCP-02"])
class AnalyticsLeastPrivilegeCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        if not rows:
            return [
                Evidence(
                    kind="sql",
                    summary=(
                        "No table grants found in system.information_schema.table_privileges"
                    ),
                    detail=_SQL,
                    rows=[],
                    ref=_REF,
                )
            ]
        r = rows[0]
        total = int(r.get("total_grants") or 0)
        user = int(r.get("user_grants") or 0)
        group = int(r.get("group_grants") or 0)
        summary = (
            f"{group} of {total} table grants go to groups or service-principals; "
            f"{user} go to individual users (grantee contains '@')"
        )
        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=[{"total_grants": total, "user_grants": user, "group_grants": group}],
                ref=_REF,
            )
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
