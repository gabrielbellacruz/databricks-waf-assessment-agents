from __future__ import annotations

from waf_agents.ai.checks.r_quality_degradation import QualityDegradationCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-R-05",
    pillar_id="r",
    title="Detect and respond to AI quality degradation",
    principle="Monitor AI endpoints for quality signals and respond to degradation",
)

# Needle: "metric_date" — unique alias in the daily quality-trend SQL
_FAKE = {
    "metric_date": [
        {"metric_date": "2024-01-01", "requests": 500, "error_count": 5, "avg_latency_ms": 200},
        {"metric_date": "2024-01-02", "requests": 520, "error_count": 6, "avg_latency_ms": 210},
        {"metric_date": "2024-01-03", "requests": 480, "error_count": 4, "avg_latency_ms": 195},
        {"metric_date": "2024-01-04", "requests": 510, "error_count": 50, "avg_latency_ms": 900},
        {"metric_date": "2024-01-05", "requests": 490, "error_count": 48, "avg_latency_ms": 850},
        {"metric_date": "2024-01-06", "requests": 500, "error_count": 52, "avg_latency_ms": 920},
        {"metric_date": "2024-01-07", "requests": 505, "error_count": 49, "avg_latency_ms": 880},
        {"metric_date": "2024-01-08", "requests": 510, "error_count": 55, "avg_latency_ms": 950},
        {"metric_date": "2024-01-09", "requests": 520, "error_count": 60, "avg_latency_ms": 980},
        {"metric_date": "2024-01-10", "requests": 500, "error_count": 58, "avg_latency_ms": 960},
        {"metric_date": "2024-01-11", "requests": 515, "error_count": 62, "avg_latency_ms": 990},
        {"metric_date": "2024-01-12", "requests": 505, "error_count": 65, "avg_latency_ms": 1000},
        {"metric_date": "2024-01-13", "requests": 510, "error_count": 70, "avg_latency_ms": 1050},
        {"metric_date": "2024-01-14", "requests": 520, "error_count": 72, "avg_latency_ms": 1080},
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
    ev = QualityDegradationCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "14 days" in ev[0].summary


def test_collect_error_rate():
    ev = QualityDegradationCheck().collect(_ctx())
    assert "overall error rate=" in ev[0].summary


def test_collect_trend_comparison():
    # 14 days => triggers first-vs-last week comparison
    ev = QualityDegradationCheck().collect(_ctx())
    assert "first-7d=" in ev[0].summary
    assert "last-7d=" in ev[0].summary


def test_collect_has_rows():
    ev = QualityDegradationCheck().collect(_ctx())
    assert len(ev[0].rows) > 0


def test_collect_note_evidence():
    ev = QualityDegradationCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "quality" in ev[1].summary.lower()


def test_collect_empty_no_crash():
    ev = QualityDegradationCheck().collect(_ctx_empty())
    assert "No serving endpoint requests" in ev[0].summary


def test_judge_maps_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "low", "score": null,'
        ' "rationale": "Rising error rate, no quality monitoring confirmed"}'
    )
    f = QualityDegradationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.sources


def test_judge_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some monitoring signals"}'
    )
    f = QualityDegradationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = QualityDegradationCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
