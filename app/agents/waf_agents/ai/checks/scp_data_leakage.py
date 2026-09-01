"""Sensitive data leakage prevention check (LLM-judged).

Answers:
  AI-SCP-01  Prevent sensitive data leakage in prompts/responses

Signals:
1. ``system.ai_gateway.usage``: PII-detected and blocked counts from AI Gateway
   guardrails — direct evidence that a content-scanning layer is active.
2. ``system.ai_gateway.usage``: guardrail-blocked request/response counts as a
   share of total calls (higher block rate suggests stricter controls).

Limitations noted:
- Guardrail configuration (which PII types are scanned, allow-vs-block policy)
  is NOT observable from usage data alone.
- Workspaces that bypass AI Gateway (direct endpoint calls) are not covered by
  this signal.  Direct endpoint usage appears in system.serving.endpoint_usage
  but PII scanning at that layer is not surfaced in system tables.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_GUARDRAIL_PII_SQL = """\
SELECT
  COUNT(*) AS total_calls,
  SUM(CASE WHEN guardrail_request_pii_detected = true THEN 1 ELSE 0 END)
      AS pii_detected_requests,
  SUM(CASE WHEN guardrail_response_pii_detected = true THEN 1 ELSE 0 END)
      AS pii_detected_responses,
  SUM(CASE WHEN guardrail_request_blocked = true THEN 1 ELSE 0 END)
      AS blocked_requests,
  SUM(CASE WHEN guardrail_response_blocked = true THEN 1 ELSE 0 END)
      AS blocked_responses
FROM system.ai_gateway.usage
WHERE timestamp >= current_timestamp() - INTERVAL 30 DAYS\
"""

_DIRECT_ENDPOINT_SQL = """\
SELECT COUNT(DISTINCT endpoint_name) AS direct_endpoints,
       SUM(request_count) AS direct_requests
FROM system.serving.endpoint_usage
WHERE window_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "AI Gateway guardrail signals (PII detection, blocked requests) confirm that a "
    "content-scanning layer is configured for gateway-routed traffic. However: "
    "(1) guardrail configuration details (which PII entity types are scanned, "
    "allow-vs-block policy, custom patterns) are not exposed in usage rows; "
    "(2) direct calls to serving endpoints that bypass AI Gateway are not covered "
    "by PII guardrails and are only visible as aggregate request counts in "
    "system.serving.endpoint_usage; (3) application-level prompt sanitisation and "
    "output filtering are not observable from system tables. A reviewer must confirm that "
    "all traffic routes through AI Gateway and that guardrail policy meets requirements."
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
            pii_req = int(g.get("pii_detected_requests") or 0)
            pii_resp = int(g.get("pii_detected_responses") or 0)
            blocked_req = int(g.get("blocked_requests") or 0)
            blocked_resp = int(g.get("blocked_responses") or 0)

            if total_calls > 0:
                guardrail_summary = (
                    f"AI Gateway: {total_calls} total calls; "
                    f"PII detected in {pii_req} request(s) and {pii_resp} response(s); "
                    f"{blocked_req} request(s) and {blocked_resp} response(s) blocked "
                    "by guardrails (last 30 days)"
                )
            else:
                guardrail_summary = (
                    "No AI Gateway usage found in the last 30 days — "
                    "PII guardrail signals unavailable"
                )
        else:
            total_calls = pii_req = pii_resp = blocked_req = blocked_resp = 0
            guardrail_summary = "No rows in system.ai_gateway.usage for the last 30 days"

        guardrail_evidence = Evidence(
            kind="sql",
            summary=guardrail_summary,
            detail=_GUARDRAIL_PII_SQL,
            rows=[{
                "total_calls": total_calls,
                "pii_detected_requests": pii_req,
                "pii_detected_responses": pii_resp,
                "blocked_requests": blocked_req,
                "blocked_responses": blocked_resp,
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
