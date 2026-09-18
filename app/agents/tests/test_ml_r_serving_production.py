from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.r_serving_production import ServingProductionCheck

_Q = Question(
    id="ML-R-01",
    pillar_id="reliability",
    title="Use scalable, production-grade model serving",
    principle="Design for failure",
)

# The query reads system.ai_gateway.usage and aliases its aggregates to
# endpoint_name / request_count / avg_latency_ms / p99_latency_ms, so these
# canned rows match the shape the SELECT produces.
_ENDPOINT_ROWS = [
    {
        "endpoint_name": "fraud-model",
        "request_count": 5000,
        "avg_latency_ms": 45.2,
        "p99_latency_ms": 120.0,
    },
    {
        "endpoint_name": "recommend-v2",
        "request_count": 3200,
        "avg_latency_ms": 62.1,
        "p99_latency_ms": 200.0,
    },
]


def _ctx(*, endpoint_rows=None, llm_response: str | None = "") -> AgentContext:
    rows = endpoint_rows if endpoint_rows is not None else _ENDPOINT_ROWS
    return AgentContext(
        assessment_id="test-ml-r01",
        layer="ml",
        sql=FakeSqlClient({"ai_gateway.usage": rows}),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_with_traffic_summarises_endpoints():
    ev = ServingProductionCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "2" in ev[0].summary  # 2 endpoints
    assert "8,200" in ev[0].summary or "8200" in ev[0].summary  # total requests


def test_collect_no_traffic_returns_zero_summary():
    ev = ServingProductionCheck().collect(_ctx(endpoint_rows=[]))
    assert "No serving endpoint traffic" in ev[0].summary


def test_collect_attaches_note_evidence():
    ev = ServingProductionCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "manual confirmation" in ev[1].summary


def test_judge_maps_llm_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium", "score": null,'
        ' "rationale": "Active endpoints observed"}'
    )
    f = ServingProductionCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_caps_high_confidence_to_medium():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "Some endpoints active"}'
    )
    f = ServingProductionCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = ServingProductionCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
