from __future__ import annotations

from waf_agents.ai.checks.pe_response_caching import ResponseCachingCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-PE-03",
    pillar_id="pe",
    title="Cache responses and embeddings where possible",
    principle="Use semantic or exact-match caching to reduce latency and cost",
)

# Needle: "route_variants" — unique alias in the ai_gateway caching SQL
_FAKE = {
    "route_variants": [
        {
            "total_gateway_requests": 20000,
            "route_variants": 4,
            "avg_gateway_latency_ms": 180.5,
        }
    ]
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
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


def test_collect_request_volume():
    ev = ResponseCachingCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "20000 gateway requests" in ev[0].summary


def test_collect_reports_avg_latency():
    ev = ResponseCachingCheck().collect(_ctx())
    assert "avg gateway latency=180.5ms" in ev[0].summary


def test_collect_cache_not_observable():
    ev = ResponseCachingCheck().collect(_ctx())
    assert "cache hit rate not directly observable" in ev[0].summary


def test_collect_has_rows():
    ev = ResponseCachingCheck().collect(_ctx())
    assert ev[0].rows[0]["total_gateway_requests"] == 20000
    assert ev[0].rows[0]["route_variants"] == 4


def test_collect_note_evidence():
    ev = ResponseCachingCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "cache" in ev[1].summary.lower()


def test_collect_empty_no_crash():
    ev = ResponseCachingCheck().collect(_ctx_empty())
    assert "No AI Gateway requests" in ev[0].summary


def test_judge_maps_verdict():
    resp = (
        '{"verdict": "unknown", "confidence": "low",'
        ' "score": null, "rationale": "Cache hit rate not observable"}'
    )
    f = ResponseCachingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN
    assert f.sources


def test_judge_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Multiple routes suggest caching"}'
    )
    f = ResponseCachingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = ResponseCachingCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
