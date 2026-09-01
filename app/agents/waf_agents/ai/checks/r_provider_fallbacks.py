"""Provider failure handling: retries and fallbacks check (LLM-judged).

Answers:
  AI-R-02  Handle provider failures with retries and fallbacks

Evidence comes from ``system.ai_gateway.usage``: provider error rate (5xx),
rate-limiting hits (429), and the number of distinct routing_information values
(a proxy for whether multiple routes / fallback endpoints are configured) over
the last 30 days.  Retry and fallback *configuration* lives in the AI Gateway
settings and is not directly readable from usage tables — the observable signal
is downstream effects (errors, route diversity).
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  COUNT(*) AS total_gateway_requests,
  SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS provider_errors,
  SUM(CASE WHEN status_code = 429 THEN 1 ELSE 0 END) AS rate_limit_hits,
  COUNT(DISTINCT routing_information) AS distinct_routes
FROM system.ai_gateway.usage
WHERE timestamp >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Retry and fallback configuration is a Mosaic AI Gateway setting that is "
    "not directly readable from system.ai_gateway.usage.  Distinct routing_information "
    "values are a weak proxy for fallback route diversity; the absence of 5xx or 429 "
    "errors does not confirm that retries are configured — it may only mean no "
    "failures occurred.  A reviewer must inspect the Gateway configuration directly."
)

_REF = "https://docs.databricks.com/en/ai-gateway/index.html"


@register(layer="ai", question_ids=["AI-R-02"])
class ProviderFallbacksCheck(Check):
    """Assess retry/fallback posture via AI Gateway usage telemetry.

    Evidence: system.ai_gateway.usage (last 30 days) — total requests, provider
    error count (5xx), rate-limit hits (429), distinct routing routes.  A note
    records that fallback configuration is not directly observable.  LLM judges.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        if rows:
            row = rows[0]
            total = int(row.get("total_gateway_requests") or 0)
            provider_errors = int(row.get("provider_errors") or 0)
            rate_limit_hits = int(row.get("rate_limit_hits") or 0)
            distinct_routes = int(row.get("distinct_routes") or 0)
        else:
            total = provider_errors = rate_limit_hits = distinct_routes = 0

        if total == 0:
            summary = (
                "No AI Gateway requests found in system.ai_gateway.usage "
                "for the last 30 days — cannot assess fallback posture"
            )
        else:
            err_pct = round(100.0 * provider_errors / total, 1)
            rl_pct = round(100.0 * rate_limit_hits / total, 1)
            summary = (
                f"{total} gateway requests in last 30 days; "
                f"provider errors (5xx): {provider_errors} ({err_pct}%), "
                f"rate-limit hits (429): {rate_limit_hits} ({rl_pct}%); "
                f"distinct routing paths: {distinct_routes}"
            )

        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=[{
                    "total_gateway_requests": total,
                    "provider_errors": provider_errors,
                    "rate_limit_hits": rate_limit_hits,
                    "distinct_routes": distinct_routes,
                }],
                ref=_REF,
            ),
            Evidence(kind="note", summary=_NOTE, rows=[], ref=_REF),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
