"""Query result cache check (LLM-judged).

Answers:
  ANA-PE-03  Leverage caching for repeated queries

SQL warehouses support a result cache: identical queries served within the cache
TTL return instantly without re-scanning data. This dramatically reduces p50
latency for dashboard refreshes and repeated BI tool queries.

Observable proxy: ``system.query.history.read_bytes_from_result_cache`` records
the number of bytes served from the result cache per query execution. A positive
value confirms that the cache was hit. The ratio of cache-hit queries to total
queries is an indirect proxy for cache leverage.

Limitation: a low cache hit rate does not always mean caching is under-utilized.
Queries with changing parameters, time filters, or non-deterministic functions
are intentionally cache-bypassed. Conversely, a high hit rate may indicate that
dashboards are stale (always reading old cached results). The LLM judge weighs
this nuance.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_CACHE_SQL = (
    "SELECT "
    "COUNT(*) AS total_queries, "
    "SUM(CASE WHEN read_bytes_from_result_cache > 0 THEN 1 ELSE 0 END) AS cache_hit_queries, "
    "SUM(read_bytes_from_result_cache) AS total_cache_bytes "
    "FROM system.query.history "
    "WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS "
    "AND execution_status = 'FINISHED' "
    "AND statement_type = 'SELECT'"
)

_NOTE = (
    "A positive read_bytes_from_result_cache indicates the result cache was hit for that "
    "query execution. However, a low cache hit rate does not necessarily indicate poor "
    "caching posture — queries with dynamic parameters, current_timestamp(), or non-"
    "deterministic functions are intentionally bypassed. Evaluating whether caching "
    "is configured correctly for repeatable dashboard queries requires manual review of "
    "warehouse caching settings and query patterns."
)

_REF = "https://docs.databricks.com/en/optimizations/disk-cache.html"


@register(layer="analytics", question_ids=["ANA-PE-03"])
class QueryCachingCheck(Check):
    """Assess result cache utilization via query history (last 30 days).

    Evidence:
      1. Cache hit ratio: queries with read_bytes_from_result_cache > 0 vs all
         finished SELECT queries.
      2. A note explaining the limitations of cache hit rate as a proxy.
    The LLM judge weighs both pieces.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_CACHE_SQL)

        if rows:
            row = rows[0]
            total_queries = int(row.get("total_queries") or 0)
            cache_hit_queries = int(row.get("cache_hit_queries") or 0)
            total_cache_bytes = int(row.get("total_cache_bytes") or 0)
        else:
            total_queries = 0
            cache_hit_queries = 0
            total_cache_bytes = 0

        if total_queries == 0:
            cache_summary = (
                "No finished SELECT queries found in system.query.history for the last 30 days"
                " — cannot assess result cache utilization"
            )
        else:
            hit_pct = round(100.0 * cache_hit_queries / total_queries, 1)
            cache_gb = round(total_cache_bytes / 1e9, 2)
            cache_summary = (
                f"Result cache (last 30 days): {cache_hit_queries} of {total_queries} "
                f"finished SELECT queries served from cache ({hit_pct}%); "
                f"{cache_gb} GB total bytes from cache"
            )

        cache_evidence = Evidence(
            kind="sql",
            summary=cache_summary,
            detail=_CACHE_SQL,
            rows=[{
                "total_queries": total_queries,
                "cache_hit_queries": cache_hit_queries,
                "total_cache_bytes": total_cache_bytes,
            }],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [cache_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
