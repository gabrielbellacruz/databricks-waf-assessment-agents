"""Token-caching check (LLM-judged).

Answers:
  AI-CO-02  Cache to reduce token consumption

Signal: system.ai_gateway.usage – the token_details struct column contains
cache_read_input_tokens and cache_creation_input_tokens.  Non-zero
cache_read_input_tokens over a 30-day window is direct evidence that prompt
caching is active and avoiding redundant token generation.

Limitation: the table is only populated when AI Gateway is configured as the
serving proxy.  An empty table means caching cannot be assessed, not that it
is absent — models may be called directly or via another gateway.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 30

_CACHE_SQL = (
    "SELECT "
    "COUNT(*) AS request_count, "
    "SUM(input_tokens) AS total_input_tokens, "
    "SUM(token_details.cache_read_input_tokens) AS cache_read_tokens, "
    "SUM(token_details.cache_creation_input_tokens) AS cache_creation_tokens, "
    "SUM(output_tokens) AS total_output_tokens "
    "FROM system.ai_gateway.usage "
    f"WHERE event_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS"
)

_NOTE = (
    "Cache-hit evidence comes from system.ai_gateway.usage.token_details. "
    "If AI Gateway is not configured the table may be empty, which does not "
    "prove caching is absent — models may be served directly or via an external proxy."
)

_REF = "https://docs.databricks.com/en/ai-gateway/index.html"


@register(layer="ai", question_ids=["AI-CO-02"])
class TokenCachingCheck(Check):
    """Assess whether prompt/response caching is active to reduce token spend.

    Queries system.ai_gateway.usage for cache_read_input_tokens and
    cache_creation_input_tokens.  Non-zero cache_read_input_tokens are strong
    evidence of active caching; zero may indicate caching is absent or that
    AI Gateway is not the serving path.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_CACHE_SQL)
        row = rows[0] if rows else {}

        request_count = int(row.get("request_count") or 0)
        total_input = int(row.get("total_input_tokens") or 0)
        cache_read = int(row.get("cache_read_tokens") or 0)
        cache_creation = int(row.get("cache_creation_tokens") or 0)
        total_output = int(row.get("total_output_tokens") or 0)

        if request_count == 0:
            cache_summary = (
                f"No AI Gateway usage found in the last {_WINDOW_DAYS} days — "
                "cannot assess token caching"
            )
            cache_pct = 0.0
        else:
            cache_pct = (
                round(100.0 * cache_read / total_input, 1) if total_input > 0 else 0.0
            )
            cache_summary = (
                f"{request_count} AI Gateway requests in the last {_WINDOW_DAYS} days; "
                f"input tokens: {total_input}, "
                f"cache_read tokens: {cache_read} ({cache_pct}%), "
                f"cache_creation tokens: {cache_creation}, "
                f"output tokens: {total_output}"
            )

        return [
            Evidence(
                kind="sql",
                summary=cache_summary,
                detail=_CACHE_SQL,
                rows=[
                    {
                        "request_count": request_count,
                        "total_input_tokens": total_input,
                        "cache_read_tokens": cache_read,
                        "cache_creation_tokens": cache_creation,
                        "cache_read_pct": cache_pct,
                    }
                ],
                ref=_REF,
            ),
            Evidence(
                kind="note",
                summary=_NOTE,
                ref=_REF,
            ),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
