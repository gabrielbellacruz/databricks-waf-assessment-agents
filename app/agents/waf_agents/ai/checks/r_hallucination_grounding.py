"""Hallucination grounding checks check (LLM-judged).

Answers:
  AI-R-04  Guard against hallucination with grounding checks

Evidence comes from ``system.serving.endpoint_usage`` grouped by served entity
name: request volumes per entity over the last 30 days.  The presence of
embedding or retrieval-type entities alongside LLM entities is a weak proxy
for a retrieval-augmented generation (RAG) pipeline.

Grounding mechanisms (retrieval augmentation, guardrails, output validation,
citation grounding) are application-level concerns that are not observable from
endpoint usage telemetry alone — this check is intentionally low-confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  served_entity_name,
  COUNT(*) AS entity_request_count,
  AVG(execution_duration_ms) AS avg_latency_ms
FROM system.serving.endpoint_usage
WHERE request_time >= current_timestamp() - INTERVAL 30 DAYS
GROUP BY served_entity_name
ORDER BY entity_request_count DESC
LIMIT 20\
"""

_NOTE = (
    "Grounding checks (retrieval augmentation, guardrails, citation validation, "
    "semantic similarity thresholds) are application-level concerns not observable "
    "from system.serving.endpoint_usage.  Embedding and retrieval entity names are "
    "a weak proxy for RAG patterns but do not confirm that hallucination grounding "
    "is actively enforced.  A reviewer must review application code and AI Gateway "
    "guardrail configuration directly."
)

_REF = "https://docs.databricks.com/en/generative-ai/retrieval-augmented-generation.html"


@register(layer="ai", question_ids=["AI-R-04"])
class HallucinationGroundingCheck(Check):
    """Assess hallucination grounding via served-entity name patterns.

    Evidence: system.serving.endpoint_usage (last 30 days) grouped by
    served_entity_name — request counts per entity type.  Presence of
    embedding/retrieval entities is a weak proxy for RAG; a note records
    that grounding is not observable from endpoint usage.  LLM judges.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if not rows:
            summary = (
                "No serving endpoint requests found in system.serving.endpoint_usage "
                "for the last 30 days — cannot assess grounding signal"
            )
        else:
            entity_names = [str(r.get("served_entity_name") or "") for r in rows]
            embedding_hint = any(
                kw in name.lower()
                for name in entity_names
                for kw in ("embed", "retriev", "rag", "bge", "e5", "minilm")
            )
            distinct_count = len(entity_names)
            hint_str = (
                "embedding/retrieval entity detected — possible RAG pipeline"
                if embedding_hint
                else "no embedding/retrieval entity names detected"
            )
            summary = (
                f"{distinct_count} distinct served entity type(s) in last 30 days; "
                f"{hint_str}"
            )

        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=rows[:10],
                ref=_REF,
            ),
            Evidence(kind="note", summary=_NOTE, rows=[], ref=_REF),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
