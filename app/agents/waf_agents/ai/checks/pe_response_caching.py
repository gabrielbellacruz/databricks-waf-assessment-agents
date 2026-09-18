"""Response and embedding caching check (LLM-judged).

Answers:
  AI-PE-03  Cache responses and embeddings where possible

Evidence comes from ``system.ai_gateway.usage``: total request volume and the
number of distinct routing variants in the last 30 days.  Volume alone is a
weak signal that caching could reduce load; distinct route count hints at
whether multiple backends (or a cache tier) are in the routing topology.

Response and embedding cache hit rates are not exposed in system tables.
Semantic caching (e.g., via Mosaic AI Gateway or an external Redis layer),
exact-match caching, and embedding pre-computation are application-level
patterns that require direct manual confirmation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  COUNT(*) AS total_gateway_requests,
  COUNT(DISTINCT routing_information) AS route_variants,
  AVG(latency_ms) AS avg_gateway_latency_ms
FROM system.ai_gateway.usage
WHERE event_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Cache hit rate for responses or embeddings is not exposed in "
    "system.ai_gateway.usage or system.serving.endpoint_usage.  Semantic caching, "
    "exact-match caching, and embedding pre-computation are application-level "
    "patterns; whether they are in place must be confirmed manually through "
    "application code review or AI Gateway configuration inspection.  High request "
    "volume is a signal that caching *could* provide value, not that it is implemented."
)

_REF = "https://docs.databricks.com/en/ai-gateway/index.html"


@register(layer="ai", question_ids=["AI-PE-03"])
class ResponseCachingCheck(Check):
    """Assess response/embedding caching via AI Gateway request patterns.

    Evidence: system.ai_gateway.usage (last 30 days) — total requests, distinct
    routing variants, avg gateway latency.  High volume is a proxy for caching
    opportunity; a note records that cache hit rate is not observable.  LLM judges.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        if rows:
            row = rows[0]
            total = int(row.get("total_gateway_requests") or 0)
            route_variants = int(row.get("route_variants") or 0)
            avg_gw_ms_raw = row.get("avg_gateway_latency_ms")
            avg_gw_ms = round(float(avg_gw_ms_raw), 1) if avg_gw_ms_raw is not None else None
        else:
            total = route_variants = 0
            avg_gw_ms = None

        if total == 0:
            summary = (
                "No AI Gateway requests found in system.ai_gateway.usage for the "
                "last 30 days — cannot assess caching opportunity or posture"
            )
        else:
            lat_str = f", avg gateway latency={avg_gw_ms}ms" if avg_gw_ms is not None else ""
            summary = (
                f"{total} gateway requests in last 30 days{lat_str}; "
                f"{route_variants} distinct routing variant(s) — "
                "cache hit rate not directly observable"
            )

        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=[{
                    "total_gateway_requests": total,
                    "route_variants": route_variants,
                    "avg_gateway_latency_ms": avg_gw_ms,
                }],
                ref=_REF,
            ),
            Evidence(kind="note", summary=_NOTE, rows=[], ref=_REF),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
