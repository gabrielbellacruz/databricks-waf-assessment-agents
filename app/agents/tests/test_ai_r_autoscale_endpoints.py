from __future__ import annotations

from waf_agents.ai.checks.r_autoscale_endpoints import AutoscaleEndpointsCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-R-03",
    pillar_id="r",
    title="Autoscale AI endpoints to demand",
    principle="Configure endpoints to scale concurrency dynamically with request load",
)

# Needle: "daily_request_count" — unique alias in the per-day GROUP BY SQL
_FAKE = {
    "daily_request_count": [
        {"request_date": "2024-01-01", "daily_request_count": 100, "avg_latency_ms": 200},
        {"request_date": "2024-01-02", "daily_request_count": 500, "avg_latency_ms": 450},
        {"request_date": "2024-01-03", "daily_request_count": 1200, "avg_latency_ms": 900},
        {"request_date": "2024-01-04", "daily_request_count": 80, "avg_latency_ms": 180},
        {"request_date": "2024-01-05", "daily_request_count": 900, "avg_latency_ms": 700},
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


def test_collect_day_count():
    ev = AutoscaleEndpointsCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "5 days" in ev[0].summary


def test_collect_min_max_avg():
    ev = AutoscaleEndpointsCheck().collect(_ctx())
    assert "min=80" in ev[0].summary
    assert "max=1200" in ev[0].summary


def test_collect_has_rows():
    ev = AutoscaleEndpointsCheck().collect(_ctx())
    assert len(ev[0].rows) > 0


def test_collect_note_evidence():
    ev = AutoscaleEndpointsCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "autoscal" in ev[1].summary.lower()


def test_collect_empty_no_crash():
    ev = AutoscaleEndpointsCheck().collect(_ctx_empty())
    assert "No serving endpoint requests" in ev[0].summary
    assert ev[0].rows == []


def test_judge_maps_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "low",'
        ' "score": null, "rationale": "High variance, autoscale unconfirmed"}'
    )
    f = AutoscaleEndpointsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.sources


def test_judge_caps_confidence():
    resp = '{"verdict": "met", "confidence": "high", "score": null, "rationale": "Stable load"}'
    f = AutoscaleEndpointsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = AutoscaleEndpointsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
