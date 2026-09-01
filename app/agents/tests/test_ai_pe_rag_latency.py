from __future__ import annotations

from waf_agents.ai.checks.pe_rag_latency import RagLatencyCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-PE-02",
    pillar_id="pe",
    title="Optimize retrieval for RAG latency",
    principle="Tune retrieval indexes and pipelines to minimize end-to-end RAG latency",
)

# Needle: "p99_latency_ms" — unique alias in the per-endpoint latency SQL
_FAKE_HIGH_LATENCY = {
    "p99_latency_ms": [
        {"endpoint_name": "vector-search-retriever", "request_count": 2000,
         "avg_latency_ms": 800, "p99_latency_ms": 4500},
        {"endpoint_name": "llm-chat-endpoint", "request_count": 3000,
         "avg_latency_ms": 400, "p99_latency_ms": 1200},
    ]
}

_FAKE_LOW_LATENCY = {
    "p99_latency_ms": [
        {"endpoint_name": "text-classifier", "request_count": 5000,
         "avg_latency_ms": 30, "p99_latency_ms": 80},
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


def test_collect_high_latency_endpoint_flagged():
    ev = RagLatencyCheck().collect(_ctx(_FAKE_HIGH_LATENCY))
    assert ev[0].kind == "sql"
    assert "1 endpoint(s) with p99 > 2000ms" in ev[0].summary


def test_collect_retrieval_hint_detected():
    ev = RagLatencyCheck().collect(_ctx(_FAKE_HIGH_LATENCY))
    assert "retrieval-type endpoint name detected" in ev[0].summary


def test_collect_no_retrieval_hint():
    ev = RagLatencyCheck().collect(_ctx(_FAKE_LOW_LATENCY))
    assert "no retrieval-type endpoint names" in ev[0].summary


def test_collect_has_rows():
    ev = RagLatencyCheck().collect(_ctx(_FAKE_HIGH_LATENCY))
    assert len(ev[0].rows) > 0


def test_collect_note_evidence():
    ev = RagLatencyCheck().collect(_ctx(_FAKE_HIGH_LATENCY))
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "retrieval" in ev[1].summary.lower()


def test_collect_empty_no_crash():
    ev = RagLatencyCheck().collect(_ctx_empty())
    assert "No serving endpoint requests" in ev[0].summary


def test_judge_maps_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "low",'
        ' "score": null, "rationale": "High p99 on retrieval endpoint"}'
    )
    f = RagLatencyCheck().run(_Q, _ctx(_FAKE_HIGH_LATENCY, llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.sources


def test_judge_caps_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Low latency"}'
    )
    f = RagLatencyCheck().run(_Q, _ctx(_FAKE_LOW_LATENCY, llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = RagLatencyCheck().run(_Q, _ctx(_FAKE_HIGH_LATENCY, llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
