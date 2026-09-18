"""Sensitive data leakage prevention check (LLM-judged).

Answers:
  AI-SCP-01  Prevent sensitive data leakage in prompts/responses

Signals:
1. ``system.ai_gateway.usage``: call volume and endpoint coverage routed through
   AI Gateway — evidence that a governed layer (where PII/content guardrails can
   be configured) fronts the traffic.
2. ``system.serving.endpoint_usage``: direct endpoint traffic that may bypass the
   gateway layer entirely.

Limitations noted:
- Per-request guardrail telemetry (PII-detected / blocked flags) is NOT exposed
  in system.ai_gateway.usage, so PII scanning cannot be confirmed from usage data.
- Workspaces that bypass AI Gateway (direct endpoint calls) are not covered by
  the gateway signal; direct endpoint usage appears in
  system.serving.endpoint_usage but PII scanning there is not surfaced.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_GUARDRAIL_PII_SQL = """\
SELECT
  COUNT(*) AS total_calls,
  COUNT(DISTINCT endpoint_name) AS gateway_endpoints,
  SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_calls
FROM system.ai_gateway.usage
WHERE event_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_DIRECT_ENDPOINT_SQL = """\
SELECT COUNT(DISTINCT se.endpoint_name) AS direct_endpoints,
       COUNT(*) AS direct_requests
FROM system.serving.endpoint_usage eu
JOIN system.serving.served_entities se
  ON eu.served_entity_id = se.served_entity_id
WHERE eu.request_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "AI Gateway routing coverage (call volume across endpoints) confirms that a "
    "governed layer is in front of gateway-routed traffic, where PII/content "
    "guardrails can be configured. However, per-request guardrail telemetry "
    "(PII-detected and blocked flags) is NOT exposed in system.ai_gateway.usage, "
    "so this check cannot confirm that PII scanning is actually configured or "
    "triggering — only that traffic is routed through the gateway. In addition: "
    "(1) direct calls to serving endpoints that bypass AI Gateway are only visible "
    "as aggregate request counts in system.serving.endpoint_usage; (2) application-"
    "level prompt sanitisation and output filtering are not observable from system "
    "tables. A reviewer must confirm that all traffic routes through AI Gateway and "
    "that guardrail policy meets requirements."
)

_REF = "https://docs.databricks.com/en/ai-gateway/configure-ai-gateway.html#guardrails"


@register(layer="ai", question_ids=["AI-SCP-01"])
class DataLeakageCheck(Check):
    """Assess sensitive-data leakage prevention via AI Gateway PII guardrail signals.

    Evidence:
    - system.ai_gateway.usage: PII-detected and blocked counts from guardrails.
    - system.serving.endpoint_usage: direct endpoint traffic that may bypass
      gateway guardrails.
    A note records guardrail-config and bypass-path limitations.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        guardrail_rows = ctx.sql.query(_GUARDRAIL_PII_SQL)
        direct_rows = ctx.sql.query(_DIRECT_ENDPOINT_SQL)

        if guardrail_rows:
            g = guardrail_rows[0]
            total_calls = int(g.get("total_calls") or 0)
            gateway_endpoints = int(g.get("gateway_endpoints") or 0)
            error_calls = int(g.get("error_calls") or 0)

            if total_calls > 0:
                guardrail_summary = (
                    f"AI Gateway: {total_calls} total call(s) across "
                    f"{gateway_endpoints} endpoint(s), {error_calls} error(s) "
                    "in the last 30 days — traffic is routed through the governed "
                    "gateway layer (per-request PII/guardrail flags not exposed)"
                )
            else:
                guardrail_summary = (
                    "No AI Gateway usage found in the last 30 days — "
                    "gateway routing signals unavailable"
                )
        else:
            total_calls = gateway_endpoints = error_calls = 0
            guardrail_summary = "No rows in system.ai_gateway.usage for the last 30 days"

        guardrail_evidence = Evidence(
            kind="sql",
            summary=guardrail_summary,
            detail=_GUARDRAIL_PII_SQL,
            rows=[{
                "total_calls": total_calls,
                "gateway_endpoints": gateway_endpoints,
                "error_calls": error_calls,
            }],
            ref=_REF,
        )

        if direct_rows:
            d = direct_rows[0]
            direct_endpoints = int(d.get("direct_endpoints") or 0)
            direct_requests = int(d.get("direct_requests") or 0)
            direct_summary = (
                f"{direct_endpoints} serving endpoint(s) with {direct_requests} direct "
                "request(s) in system.serving.endpoint_usage (last 30 days); "
                "these calls may bypass AI Gateway guardrails"
            )
        else:
            direct_endpoints = 0
            direct_requests = 0
            direct_summary = "No direct serving endpoint usage found for the last 30 days"

        direct_evidence = Evidence(
            kind="sql",
            summary=direct_summary,
            detail=_DIRECT_ENDPOINT_SQL,
            rows=[{"direct_endpoints": direct_endpoints, "direct_requests": direct_requests}],
            ref="https://docs.databricks.com/en/admin/system-tables/serving.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [guardrail_evidence, direct_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
