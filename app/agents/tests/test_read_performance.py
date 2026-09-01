from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.read_performance import ReadPerformanceCheck

_Q = Question(
    id="STO-PE-05",
    pillar_id="performance-efficiency",
    title="Monitor read performance on stored tables",
    principle="Ensure read query performance is visible and tracked",
)

# Needle: "read_query_count" appears as an alias in ReadPerformanceCheck._SQL.
_FAKE_RESPONSES = {
    "read_query_count": [
        {
            "read_query_count": 250,
            "avg_duration_ms": 4500.0,
            "max_duration_ms": 95000,
            "slow_query_count": 12,
        }
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_two_evidences():
    ev = ReadPerformanceCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    assert ev[1].kind == "note"


def test_collect_sql_summary_contains_query_count():
    ev = ReadPerformanceCheck().collect(_ctx())
    assert "250 SELECT queries" in ev[0].summary


def test_collect_sql_summary_contains_duration_stats():
    ev = ReadPerformanceCheck().collect(_ctx())
    assert "avg=4500.0ms" in ev[0].summary
    assert "max=95000ms" in ev[0].summary


def test_collect_sql_summary_contains_slow_query_info():
    ev = ReadPerformanceCheck().collect(_ctx())
    # 12 slow out of 250 = 4.8%
    assert "slow queries (>30s): 12" in ev[0].summary
    assert "4.8%" in ev[0].summary


def test_collect_sql_evidence_has_rows():
    ev = ReadPerformanceCheck().collect(_ctx())
    row = ev[0].rows[0]
    assert row["read_query_count"] == 250
    assert row["avg_duration_ms"] == 4500.0
    assert row["slow_query_count"] == 12


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Telemetry present but no dashboard confirmed"}'
    )
    f = ReadPerformanceCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Rich query telemetry available with slow-query tracking"}'
    )
    f = ReadPerformanceCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = ReadPerformanceCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
