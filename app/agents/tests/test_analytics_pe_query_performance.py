from __future__ import annotations

from waf_agents.analytics.checks.pe_query_performance import QueryPerformanceCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-PE-05",
    pillar_id="performance-efficiency",
    title="Monitor query performance and slow dashboards",
    principle="Ensure analytics query performance is visible and tracked",
)

# Needle: "total_queries" as an alias appears uniquely in _SQL
_FAKE_RESPONSES = {
    "total_queries": [
        {
            "total_queries": 300,
            "slow_queries": 18,
            "failed_queries": 5,
            "avg_duration_ms": 6200.0,
            "max_duration_ms": 120_000,
        }
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_two_evidences():
    ev = QueryPerformanceCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    assert ev[1].kind == "note"


def test_collect_summary_contains_query_count():
    ev = QueryPerformanceCheck().collect(_ctx())
    assert "300 SELECT queries" in ev[0].summary


def test_collect_summary_contains_duration_stats():
    ev = QueryPerformanceCheck().collect(_ctx())
    assert "avg=6200.0ms" in ev[0].summary
    assert "max=120000ms" in ev[0].summary


def test_collect_summary_contains_slow_query_info():
    ev = QueryPerformanceCheck().collect(_ctx())
    # 18/300 = 6.0%
    assert "slow queries (>30s): 18" in ev[0].summary
    assert "6.0%" in ev[0].summary


def test_collect_summary_contains_failed_count():
    ev = QueryPerformanceCheck().collect(_ctx())
    assert "failed: 5" in ev[0].summary


def test_collect_evidence_rows():
    ev = QueryPerformanceCheck().collect(_ctx())
    row = ev[0].rows[0]
    assert row["total_queries"] == 300
    assert row["slow_queries"] == 18
    assert row["failed_queries"] == 5
    assert row["avg_duration_ms"] == 6200.0


def test_judge_maps_llm_verdict_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Telemetry present but no dashboard confirmed"}'
    )
    f = QueryPerformanceCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Rich query telemetry with slow-query tracking active"}'
    )
    f = QueryPerformanceCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET


def test_no_llm_degrades_to_unassessed():
    f = QueryPerformanceCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
