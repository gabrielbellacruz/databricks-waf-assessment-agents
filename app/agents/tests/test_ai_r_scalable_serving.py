from __future__ import annotations

from waf_agents.ai.checks.r_scalable_serving import ScalableServingCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-R-01",
    pillar_id="r",
    title="Use scalable, production-grade model serving",
    principle="Ensure AI endpoints are production-ready and can absorb demand",
)

_FAKE = {
    "total_requests": [
        {
            "endpoint_count": 3,
            "total_requests": 5000,
            "avg_latency_ms": 250.5,
            "p95_latency_ms": 800.0,
            "server_error_count": 10,
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


def test_collect_reports_endpoint_count():
    ev = ScalableServingCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "3 active endpoint(s)" in ev[0].summary
    assert "5000 requests" in ev[0].summary


def test_collect_reports_latency():
    ev = ScalableServingCheck().collect(_ctx())
    assert "avg=250.5ms" in ev[0].summary
    assert "p95=800.0ms" in ev[0].summary


def test_collect_reports_error_rate():
    ev = ScalableServingCheck().collect(_ctx())
    assert "server errors: 10" in ev[0].summary


def test_collect_has_rows():
    ev = ScalableServingCheck().collect(_ctx())
    assert ev[0].rows and ev[0].rows[0]["total_requests"] == 5000


def test_collect_note_evidence():
    ev = ScalableServingCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "not" in ev[1].summary.lower()


def test_collect_empty_no_crash():
    ev = ScalableServingCheck().collect(_ctx_empty())
    assert "No serving endpoint requests" in ev[0].summary


def test_judge_maps_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Some endpoints active"}'
    )
    f = ScalableServingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_caps_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Endpoints active"}'
    )
    f = ScalableServingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = ScalableServingCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
