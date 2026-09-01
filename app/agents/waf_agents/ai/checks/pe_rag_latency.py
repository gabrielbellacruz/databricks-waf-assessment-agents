"""RAG retrieval latency optimisation check (LLM-judged).

Answers:
  AI-PE-02  Optimize retrieval for RAG latency

Evidence comes from ``system.serving.endpoint_usage`` grouped by endpoint:
per-endpoint p99 latency over the last 30 days.  High p99 latency — especially
on endpoints whose names suggest embedding or retrieval — is a proxy for
potential retrieval bottlenecks in a RAG pipeline.

RAG retrieval optimisation (chunk size, embedding dimensionality, index type,
approximate-nearest-neighbour algorithm, reranking stage) is an application-
and index-level concern not directly observable from endpoint latency alone.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  endpoint_name,
  COUNT(*) AS request_count,
  AVG(execution_duration_ms) AS avg_latency_ms,
  percentile_approx(execution_duration_ms, 0.99) AS p99_latency_ms
FROM system.serving.endpoint_usage
WHERE request_time >= current_timestamp() - INTERVAL 30 DAYS
GROUP BY endpoint_name
ORDER BY p99_latency_ms DESC NULLS LAST
LIMIT 10\
"""

_NOTE = (
    "RAG retrieval latency is shaped by chunk size, embedding model, index type "
    "(HNSW vs IVF), approximate-nearest-neighbour tuning, and optional reranking. "
    "These are application- and index-level settings not readable from "
    "system.serving.endpoint_usage.  High p99 latency on embedding or retrieval "
    "endpoints is an indirect signal, but proving optimisation is in place "
    "requires manual review of the pipeline and Databricks Vector Search configuration."
)

_REF = "https://docs.databricks.com/en/generative-ai/vector-search.html"


@register(layer="ai", question_ids=["AI-PE-02"])
class RagLatencyCheck(Check):
    """Assess RAG retrieval latency via per-endpoint p99 latency.

    Evidence: system.serving.endpoint_usage (last 30 days) grouped by endpoint
    — request count, avg latency, p99 latency (top 10 by p99).  High latency on
    retrieval-type endpoints is a weak proxy for unoptimised retrieval.  A note
    records that retrieval configuration is not observable.  LLM judges.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if not rows:
            summary = (
                "No serving endpoint requests found in system.serving.endpoint_usage "
                "for the last 30 days — cannot assess RAG retrieval latency"
            )
        else:
            high_latency_threshold_ms = 2_000
            high_latency = [
                r for r in rows
                if (r.get("p99_latency_ms") or 0) > high_latency_threshold_ms
            ]
            names = [str(r.get("endpoint_name") or "") for r in rows]
            retrieval_hint = any(
                kw in n.lower()
                for n in names
                for kw in ("embed", "retriev", "rag", "search", "vector")
            )
            hint_str = (
                "retrieval-type endpoint name detected"
                if retrieval_hint
                else "no retrieval-type endpoint names"
            )
            summary = (
                f"{len(rows)} endpoint(s) with data; "
                f"{len(high_latency)} endpoint(s) with p99 > {high_latency_threshold_ms}ms; "
                f"{hint_str}"
            )

        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=rows[:10] if rows else [],
                ref=_REF,
            ),
            Evidence(kind="note", summary=_NOTE, rows=[], ref=_REF),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
