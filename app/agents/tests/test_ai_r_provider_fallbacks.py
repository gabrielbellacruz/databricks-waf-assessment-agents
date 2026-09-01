from __future__ import annotations

from waf_agents.ai.checks.r_provider_fallbacks import ProviderFallbacksCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-R-02",
    pillar_id="r",
    title="Handle provider failures with retries and fallbacks",
    principle="Ensure AI calls are resilient to upstream provider failures",
)

# Needle: "provider_errors" — unique substring of the ai_gateway.usage SQL alias
_FAKE = {
    "provider_errors": [
        {
            "total_gateway_requests": 10000,
            "provider_errors": 150,
            "rate_limit_hits": 40,
            "distinct_routes": 3,
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


def test_collect_reports_request_volume():
    ev = ProviderFallbacksCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "10000 gateway requests" in ev[0].summary


def test_collect_reports_error_counts():
    ev = ProviderFallbacksCheck().collect(_ctx())
    assert "provider errors (5xx): 150" in ev[0].summary
    assert "rate-limit hits (429): 40" in ev[0].summary


def test_collect_reports_distinct_routes():
    ev = ProviderFallbacksCheck().collect(_ctx())
    assert "3" in ev[0].summary


def test_collect_has_rows():
    ev = ProviderFallbacksCheck().collect(_ctx())
    assert ev[0].rows[0]["distinct_routes"] == 3


def test_collect_note_evidence():
    ev = ProviderFallbacksCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "fallback" in ev[1].summary.lower()


def test_collect_empty_no_crash():
    ev = ProviderFallbacksCheck().collect(_ctx_empty())
    assert "No AI Gateway requests" in ev[0].summary


def test_judge_maps_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "low",'
        ' "score": null, "rationale": "High error rate, no fallback evidence"}'
    )
    f = ProviderFallbacksCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.LOW


def test_judge_caps_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Multiple routes"}'
    )
    f = ProviderFallbacksCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = ProviderFallbacksCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
