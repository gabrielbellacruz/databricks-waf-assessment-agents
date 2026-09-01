from __future__ import annotations

from waf_agents.ai.checks.r_hallucination_grounding import HallucinationGroundingCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-R-04",
    pillar_id="r",
    title="Guard against hallucination with grounding checks",
    principle="Use retrieval augmentation or guardrails to reduce hallucinated responses",
)

# Needle: "entity_request_count" — unique alias in the served_entity_name GROUP BY SQL
_FAKE_WITH_EMBED = {
    "entity_request_count": [
        {"served_entity_name": "llama-3-70b-instruct", "entity_request_count": 3000,
         "avg_latency_ms": 400},
        {"served_entity_name": "bge-large-embedding", "entity_request_count": 2800,
         "avg_latency_ms": 50},
        {"served_entity_name": "rag-retrieval-endpoint", "entity_request_count": 2700,
         "avg_latency_ms": 120},
    ]
}

_FAKE_NO_EMBED = {
    "entity_request_count": [
        {"served_entity_name": "gpt-4o-mini", "entity_request_count": 5000, "avg_latency_ms": 600},
    ]
}


def _ctx(fake: dict, *, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(fake),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def _ctx_empty(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_detects_embedding_hint():
    ev = HallucinationGroundingCheck().collect(_ctx(_FAKE_WITH_EMBED))
    assert ev[0].kind == "sql"
    assert "embedding/retrieval entity detected" in ev[0].summary


def test_collect_no_embedding_hint():
    ev = HallucinationGroundingCheck().collect(_ctx(_FAKE_NO_EMBED))
    assert "no embedding/retrieval entity names detected" in ev[0].summary


def test_collect_distinct_entity_count():
    ev = HallucinationGroundingCheck().collect(_ctx(_FAKE_WITH_EMBED))
    assert "3 distinct served entity type(s)" in ev[0].summary


def test_collect_has_rows():
    ev = HallucinationGroundingCheck().collect(_ctx(_FAKE_WITH_EMBED))
    assert len(ev[0].rows) > 0


def test_collect_note_evidence():
    ev = HallucinationGroundingCheck().collect(_ctx(_FAKE_WITH_EMBED))
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "grounding" in ev[1].summary.lower()


def test_collect_empty_no_crash():
    ev = HallucinationGroundingCheck().collect(_ctx_empty())
    assert "No serving endpoint requests" in ev[0].summary


def test_judge_maps_verdict():
    resp = (
        '{"verdict": "unknown", "confidence": "low", "score": null,'
        ' "rationale": "Embedding hint present but grounding unconfirmed"}'
    )
    f = HallucinationGroundingCheck().run(_Q, _ctx(_FAKE_WITH_EMBED, llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN
    assert f.sources


def test_judge_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "RAG pattern detected"}'
    )
    f = HallucinationGroundingCheck().run(_Q, _ctx(_FAKE_WITH_EMBED, llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = HallucinationGroundingCheck().run(_Q, _ctx(_FAKE_WITH_EMBED, llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
