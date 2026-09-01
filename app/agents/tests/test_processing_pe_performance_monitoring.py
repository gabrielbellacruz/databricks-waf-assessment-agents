from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.pe_performance_monitoring import PerformanceMonitoringCheck

_Q = Question(
    id="PRO-PE-05",
    pillar_id="performance-efficiency",
    title="Monitor pipeline and job performance",
    principle="Continuously optimise processing performance",
)

# needle "distinct_runs" -> pe_performance_monitoring SQL (unique to that module)
_SQL_ROWS = [
    {
        "total_runs": 60,
        "distinct_runs": 30,
        "failed_runs": 4,
        "avg_run_seconds": 900.0,
    }
]

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "Regular job runs with low failure rate suggest active monitoring."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "medium", "score": null,'
    ' "rationale": "Jobs running but failure rate suggests incomplete monitoring."}'
)


def _ctx(*, llm_response: str | None = _LLM_MET, rows: list[dict] | None = None) -> AgentContext:
    sql_rows = _SQL_ROWS if rows is None else rows
    return AgentContext(
        assessment_id="test-assessment",
        layer="processing",
        sql=FakeSqlClient({"distinct_runs": sql_rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_two_evidence_entries():
    ev = PerformanceMonitoringCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_counts():
    ev = PerformanceMonitoringCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert sql_ev.rows[0]["total_runs"] == 60
    assert sql_ev.rows[0]["distinct_runs"] == 30
    assert sql_ev.rows[0]["failed_runs"] == 4


def test_collect_summary_mentions_failure_pct():
    ev = PerformanceMonitoringCheck().collect(_ctx())
    # 4 / 60 ≈ 6.7%
    assert "6.7%" in ev[0].summary


def test_collect_note_mentions_alert_config():
    ev = PerformanceMonitoringCheck().collect(_ctx())
    note_ev = ev[1]
    assert note_ev.kind == "note"
    assert note_ev.rows == []
    assert "notification" in note_ev.summary.lower() or "alert" in note_ev.summary.lower()


def test_collect_no_runs():
    ctx = AgentContext(
        assessment_id="t2",
        layer="processing",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = PerformanceMonitoringCheck().collect(ctx)
    assert "No job runs found" in ev[0].summary
    assert ev[0].rows[0]["total_runs"] == 0


def test_judge_met_verdict():
    f = PerformanceMonitoringCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_partial_verdict():
    f = PerformanceMonitoringCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL


def test_judge_confidence_capped_at_medium():
    high_conf = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "good run cadence"}'
    )
    f = PerformanceMonitoringCheck().run(_Q, _ctx(llm_response=high_conf))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_sql_and_note():
    f = PerformanceMonitoringCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


def test_no_llm_degrades_to_unassessed():
    f = PerformanceMonitoringCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
