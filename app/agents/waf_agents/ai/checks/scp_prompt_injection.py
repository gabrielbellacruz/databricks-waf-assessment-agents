"""Prompt injection and misuse defense check (LLM-judged).

Answers:
  AI-SCP-02  Defend against prompt injection and misuse

Signals:
1. ``system.ai_gateway.usage``: guardrail-blocked request count and rate —
   blocked requests indicate an active defense layer is operating.
2. ``system.ai_gateway.usage``: 4xx client-error rate as a proxy for rejected
   malformed or policy-violating requests.

Limitations noted:
- AI Gateway guardrails provide keyword/regex blocking and safety classifiers
  but do NOT surface which injection patterns were detected.
- Prompt injection is a semantic attack; keyword-based guardrails may not catch
  sophisticated injection attempts.
- Application-level input validation and output filtering (e.g. LangChain
  guardrails, custom sanitisation) are not observable from system tables.
- Workspaces calling endpoints directly (bypassing AI Gateway) have no
  observable guardrail coverage.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_GUARDRAIL_BLOCK_SQL = """\
SELECT
  COUNT(*) AS total_calls,
  SUM(CASE WHEN guardrail_request_blocked = true THEN 1 ELSE 0 END)
      AS request_blocked,
  SUM(CASE WHEN guardrail_response_blocked = true THEN 1 ELSE 0 END)
      AS response_blocked,
  SUM(CASE WHEN status_code >= 400 AND status_code < 500 THEN 1 ELSE 0 END)
      AS client_errors
FROM system.ai_gateway.usage
WHERE timestamp >= current_timestamp() - INTERVAL 30 DAYS\
"""

_ENDPOINT_ERRORS_SQL = """\
SELECT
  SUM(request_count) AS total_requests,
  SUM(CASE WHEN status_code >= 400 AND status_code < 500 THEN request_count ELSE 0 END)
      AS client_error_requests
FROM system.serving.endpoint_usage
WHERE window_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "AI Gateway guardrail blocking is the primary observable signal for prompt-injection "
    "defense, but guardrail configuration details (safety categories, custom patterns, "
    "allow-list vs block-list) are not exposed in system.ai_gateway.usage rows. "
    "Prompt injection is a semantic attack; guardrail block counts confirm a policy is "
    "in place but cannot confirm it catches sophisticated injections. "
    "Application-level defenses (input sanitisation, context boundaries, output parsing) "
    "and rate limiting are not observable from system tables. A reviewer must verify that "
    "guardrail policy covers prompt injection patterns and that all AI traffic routes "
    "through AI Gateway."
)

_REF = "https://docs.databricks.com/en/ai-gateway/configure-ai-gateway.html#guardrails"


@register(layer="ai", question_ids=["AI-SCP-02"])
class PromptInjectionCheck(Check):
    """Assess prompt injection and misuse defenses via AI Gateway guardrail block rates.

    Evidence:
    - system.ai_gateway.usage: guardrail-blocked counts and 4xx client-error rates.
    - system.serving.endpoint_usage: client-error rate on direct endpoint traffic.
    A note records the limits of guardrail coverage as an injection-defense proxy.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        guardrail_rows = ctx.sql.query(_GUARDRAIL_BLOCK_SQL)
        endpoint_rows = ctx.sql.query(_ENDPOINT_ERRORS_SQL)

        if guardrail_rows:
            g = guardrail_rows[0]
            total_calls = int(g.get("total_calls") or 0)
            request_blocked = int(g.get("request_blocked") or 0)
            response_blocked = int(g.get("response_blocked") or 0)
            client_errors = int(g.get("client_errors") or 0)

            if total_calls > 0:
                block_pct = round(100.0 * (request_blocked + response_blocked) / total_calls, 1)
                guardrail_summary = (
                    f"AI Gateway: {total_calls} calls; "
                    f"{request_blocked} request(s) and {response_blocked} response(s) "
                    f"guardrail-blocked ({block_pct}% block rate); "
                    f"{client_errors} 4xx client error(s) in the last 30 days"
                )
            else:
                guardrail_summary = (
                    "No AI Gateway usage in the last 30 days — "
                    "guardrail block signals unavailable"
                )
        else:
            total_calls = request_blocked = response_blocked = client_errors = 0
            guardrail_summary = "No rows in system.ai_gateway.usage for the last 30 days"

        guardrail_evidence = Evidence(
            kind="sql",
            summary=guardrail_summary,
            detail=_GUARDRAIL_BLOCK_SQL,
            rows=[{
                "total_calls": total_calls,
                "request_blocked": request_blocked,
                "response_blocked": response_blocked,
                "client_errors": client_errors,
            }],
            ref=_REF,
        )

        if endpoint_rows:
            e = endpoint_rows[0]
            total_requests = int(e.get("total_requests") or 0)
            client_error_requests = int(e.get("client_error_requests") or 0)
            err_pct = (
                round(100.0 * client_error_requests / total_requests, 1)
                if total_requests > 0 else 0.0
            )
            endpoint_summary = (
                f"Direct serving endpoint traffic: {total_requests} requests, "
                f"{client_error_requests} client errors ({err_pct}%) "
                "in the last 30 days — these bypass AI Gateway guardrails"
            )
        else:
            total_requests = 0
            client_error_requests = 0
            endpoint_summary = (
                "No direct serving endpoint usage found in "
                "system.serving.endpoint_usage for the last 30 days"
            )

        endpoint_evidence = Evidence(
            kind="sql",
            summary=endpoint_summary,
            detail=_ENDPOINT_ERRORS_SQL,
            rows=[{
                "total_requests": total_requests,
                "client_error_requests": client_error_requests,
            }],
            ref="https://docs.databricks.com/en/admin/system-tables/serving.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [guardrail_evidence, endpoint_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
