"""Access control for AI assets check (LLM-judged).

Answers:
  AI-DG-03  Control access to models, endpoints, and knowledge bases

Signal:
  1. system.information_schema.routine_privileges — grants on UC functions/tools
     broken down by group vs individual-user grantees (same heuristic as
     ingestion access_control: grantee containing '@' is an individual user).
  2. system.ai_gateway.usage — rows present indicate AI Gateway is routing
     requests; guardrail_triggered column signals active content controls.

Limitation note: Serving endpoint ACLs (CAN_QUERY, CAN_MANAGE) are not exposed
through system.information_schema.* and are not visible to the SP's system-table
queries. Assess via the Databricks UI or the Serving Endpoints REST API.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_ROUTINE_PRIVS_SQL = (
    "SELECT COUNT(*) AS routine_grants,"
    " SUM(CASE WHEN grantee LIKE '%@%' THEN 1 ELSE 0 END) AS user_grants,"
    " SUM(CASE WHEN grantee NOT LIKE '%@%' THEN 1 ELSE 0 END) AS group_grants"
    " FROM system.information_schema.routine_privileges"
    " WHERE routine_catalog <> 'hive_metastore'"
)

_GATEWAY_SQL = (
    "SELECT COUNT(*) AS gateway_governed_total,"
    " SUM(CASE WHEN guardrail_triggered = TRUE THEN 1 ELSE 0 END) AS guardrail_triggered"
    " FROM system.ai_gateway.usage"
    " WHERE CAST(window_start_time AS DATE) >= CURRENT_DATE - INTERVAL 30 DAYS"
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/service-models.html"

_ENDPOINT_ACL_LIMITATION = (
    "Serving endpoint permission levels (CAN_QUERY, CAN_MANAGE) are not exposed"
    " through system.information_schema and are not accessible to the SP's"
    " system-table queries. Review endpoint ACLs via the Databricks UI or"
    " GET /api/2.0/permissions/serving-endpoints/{id}."
)


@register(layer="ai", question_ids=["AI-DG-03"])
class AiAccessControlCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        priv_rows = ctx.sql.query(_ROUTINE_PRIVS_SQL)
        gateway_rows = ctx.sql.query(_GATEWAY_SQL)

        p = priv_rows[0] if priv_rows else {}
        total_grants = int(p.get("routine_grants") or 0)
        user_grants = int(p.get("user_grants") or 0)
        group_grants = int(p.get("group_grants") or 0)

        g = gateway_rows[0] if gateway_rows else {}
        gateway_total = int(g.get("gateway_governed_total") or 0)
        guardrail_count = int(g.get("guardrail_triggered") or 0)

        priv_evidence = Evidence(
            kind="sql",
            summary=(
                f"{group_grants} of {total_grants} UC function grant(s) go to"
                f" groups/service-principals; {user_grants} to individual users"
            ),
            detail=_ROUTINE_PRIVS_SQL,
            rows=[{
                "routine_grants": total_grants,
                "user_grants": user_grants,
                "group_grants": group_grants,
            }],
            ref=_REF,
        )
        gateway_evidence = Evidence(
            kind="sql",
            summary=(
                f"{gateway_total} AI Gateway request(s) in last 30 days;"
                f" {guardrail_count} triggered a guardrail (content control active)"
            ),
            detail=_GATEWAY_SQL,
            rows=[{
                "gateway_governed_total": gateway_total,
                "guardrail_triggered": guardrail_count,
            }],
            ref=_REF,
        )
        limitation = Evidence(
            kind="uc_metadata",
            summary=_ENDPOINT_ACL_LIMITATION,
            detail="Verify endpoint ACLs via the Serving Endpoints REST API or Databricks UI.",
            ref=_REF,
        )
        return [priv_evidence, gateway_evidence, limitation]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
