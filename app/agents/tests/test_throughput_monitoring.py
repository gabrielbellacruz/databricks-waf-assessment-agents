from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.throughput_monitoring import ThroughputMonitoringCheck

_Q = Question(
    id="ING-PE-05",
    pillar_id="performance-efficiency",
    title="Monitor ingestion throughput and latency",
    principle="Optimize workload performance",
)

# Canned SQL rows: 20 run intervals, 5 distinct runs, ~120 s avg duration.
_SQL_ROWS = [{"total_runs": 20, "distinct_runs": 5, "avg_run_seconds": 120.5}]

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "Jobs run regularly, indicating throughput is observed."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "low", "score": null,'
    ' "rationale": "No run activity; throughput monitoring cannot be confirmed."}'
)


def _ctx(*, llm_response: str | None = _LLM_MET, runs: list[dict] | None = None) -> AgentContext:
    sql_rows = _SQL_ROWS if runs is None else runs
    return AgentContext(
        assessment_id="test-assessment",
        layer="ingestion",
        sql=FakeSqlClient({"job_run_timeline": sql_rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_two_evidence_entries():
    ev = ThroughputMonitoringCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_kind_and_content():
    ev = ThroughputMonitoringCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert "20" in sql_ev.summary  # total_runs
    assert "5" in sql_ev.summary   # distinct_runs
    assert sql_ev.rows[0]["total_runs"] == 20
    assert sql_ev.rows[0]["distinct_runs"] == 5
    assert sql_ev.rows[0]["avg_run_seconds"] == 120.5


def test_collect_note_evidence_kind_and_no_rows():
    ev = ThroughputMonitoringCheck().collect(_ctx())
    note_ev = ev[1]
    assert note_ev.kind == "note"
    assert note_ev.rows == []
    assert note_ev.ref == "https://docs.databricks.com/en/optimizations/index.html"


def test_collect_note_summary_mentions_throughput():
    ev = ThroughputMonitoringCheck().collect(_ctx())
    assert "throughput" in ev[1].summary.lower()


def test_collect_note_summary_mentions_sa_confirmation():
    ev = ThroughputMonitoringCheck().collect(_ctx())
    assert "manual confirmation" in ev[1].summary


def test_collect_no_runs_reports_zero():
    ev = ThroughputMonitoringCheck().collect(_ctx(runs=[]))
    assert ev[0].rows[0]["total_runs"] == 0
    assert ev[0].rows[0]["distinct_runs"] == 0
    assert "No job runs found" in ev[0].summary


def test_collect_zero_row_result_is_handled():
    """FakeSqlClient returns [] when no needle matches; must not raise."""
    ctx = AgentContext(
        assessment_id="t2",
        layer="ingestion",
        sql=FakeSqlClient({}),  # no key matches -> returns []
        catalogs=[],
        llm=None,
    )
    ev = ThroughputMonitoringCheck().collect(ctx)
    assert ev[0].rows[0]["total_runs"] == 0


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_met_verdict_mapped():
    f = ThroughputMonitoringCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources  # evidence attached


def test_judge_not_met_verdict_mapped():
    f = ThroughputMonitoringCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.LOW


def test_judge_confidence_capped_at_medium_when_llm_claims_high():
    high_conf = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "Jobs run but no explicit monitoring dashboard."}'
    )
    f = ThroughputMonitoringCheck().run(_Q, _ctx(llm_response=high_conf))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_both_evidence_entries():
    f = ThroughputMonitoringCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = ThroughputMonitoringCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached even without LLM
