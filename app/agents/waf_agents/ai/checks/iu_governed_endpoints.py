"""Governed AI endpoints and tools exposure check (LLM-judged).

Answers:
  AI-IU-04  Expose AI functionality through governed endpoints/tools

Signal:
  1. system.serving.endpoint_usage — active serving endpoints (request counts)
     confirm that AI functionality is exposed via Model Serving.
  2. system.ai_gateway.usage — calls routed through AI Gateway confirm that
     endpoints are governed (rate limits, guardrails, logging applied).
  3. system.information_schema.routines — UC-registered functions/tools confirm
     that AI capabilities are exposed as governed, discoverable UC assets.

Limitation note: Whether a serving endpoint is properly ACL'd (governed access)
vs open to all workspace users is not exposed through system tables. AI Gateway
governance configuration (route rules, guardrails, rate limits) requires review
via the AI Gateway REST API or Databricks UI.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SERVING_SQL = (
    "SELECT COUNT(DISTINCT endpoint_name) AS governed_endpoint_requests,"
    " SUM(request_count) AS total_endpoint_requests"
    " FROM system.serving.endpoint_usage"
    " WHERE CAST(window_start_time AS DATE) >= CURRENT_DATE - INTERVAL 30 DAYS"
)

_GATEWAY_SQL = (
    "SELECT COUNT(*) AS gateway_governed_calls,"
    " COUNT(DISTINCT endpoint_name) AS gateway_endpoints"
    " FROM system.ai_gateway.usage"
    " WHERE CAST(window_start_time AS DATE) >= CURRENT_DATE - INTERVAL 30 DAYS"
)

_ROUTINES_SQL = (
    "SELECT COUNT(*) AS ai_tool_routines,"
    " COUNT(DISTINCT routine_catalog) AS ai_tool_catalogs"
    " FROM system.information_schema.routines"
    " WHERE routine_catalog <> 'hive_metastore'"
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/manage-serving-endpoints.html"

_GOVERNANCE_LIMITATION = (
    "Serving endpoint permission levels (CAN_QUERY, CAN_MANAGE) are not exposed"
    " in system tables. AI Gateway governance config (guardrails, rate limits,"
    " input/output filtering) requires review via the AI Gateway REST API."
    " UC registered tools may not enumerate all deployed AI capabilities."
)


@register(layer="ai", question_ids=["AI-IU-04"])
class AiGovernedEndpointsCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        serving_rows = ctx.sql.query(_SERVING_SQL)
        gateway_rows = ctx.sql.query(_GATEWAY_SQL)
        routine_rows = ctx.sql.query(_ROUTINES_SQL)

        s = serving_rows[0] if serving_rows else {}
        active_endpoints = int(s.get("governed_endpoint_requests") or 0)
        total_requests = int(s.get("total_endpoint_requests") or 0)

        g = gateway_rows[0] if gateway_rows else {}
        gateway_calls = int(g.get("gateway_governed_calls") or 0)
        gateway_endpoints = int(g.get("gateway_endpoints") or 0)

        r = routine_rows[0] if routine_rows else {}
        ai_tools = int(r.get("ai_tool_routines") or 0)
        ai_catalogs = int(r.get("ai_tool_catalogs") or 0)

        serving_evidence = Evidence(
            kind="sql",
            summary=(
                f"{active_endpoints} active serving endpoint(s) with"
                f" {total_requests} request(s) in the last 30 days"
            ),
            detail=_SERVING_SQL,
            rows=[{
                "governed_endpoint_requests": active_endpoints,
                "total_endpoint_requests": total_requests,
            }],
            ref=_REF,
        )
        gateway_evidence = Evidence(
            kind="sql",
            summary=(
                f"{gateway_calls} AI Gateway call(s) across {gateway_endpoints}"
                " endpoint(s) in the last 30 days (governance layer active)"
            ),
            detail=_GATEWAY_SQL,
            rows=[{
                "gateway_governed_calls": gateway_calls,
                "gateway_endpoints": gateway_endpoints,
            }],
            ref=_REF,
        )
        routine_evidence = Evidence(
            kind="sql",
            summary=(
                f"{ai_tools} UC-registered function(s)/tool(s) across {ai_catalogs}"
                " catalog(s) (AI tools as governed UC assets)"
            ),
            detail=_ROUTINES_SQL,
            rows=[{"ai_tool_routines": ai_tools, "ai_tool_catalogs": ai_catalogs}],
            ref=_REF,
        )
        limitation = Evidence(
            kind="uc_metadata",
            summary=_GOVERNANCE_LIMITATION,
            detail=(
                "Review serving endpoint ACLs and AI Gateway route configs via"
                " the Databricks UI or REST API to verify governance completeness."
            ),
            ref=_REF,
        )
        return [serving_evidence, gateway_evidence, routine_evidence, limitation]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
