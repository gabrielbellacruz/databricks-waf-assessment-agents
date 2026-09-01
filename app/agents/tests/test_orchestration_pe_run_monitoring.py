from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.pe_run_monitoring import OrcRunMonitoringCheck

_Q = Question(
    id="ORC-PE-04",
    pillar_id="performance-efficiency",
    title="Monitor workflow run durations and trends",
    principle="Continuously optimize workload performance",
)

# Needle: "min_run_seconds" is unique to pe_run_monitoring SQL (pe_polling_idle doesn't have min)
_SQL_ROWS = [{
    "total_runs": 120,
    "distinct_runs": 60,
    "avg_run_seconds": 300.0,
    "max_run_seconds": 900.0,
    "min_run_seconds": 180.0,
}]

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "60 distinct runs tracked; duration data available for monitoring."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "low", "score": null,'
    ' "rationale": "No monitoring evidence found in system tables."}'
)


def _ctx(
    *,
    llm_response: str | None = _LLM_MET,
    rows: list[dict] | None = None,
) -> AgentContext:
    sql_rows = _SQL_ROWS if rows is None else rows
    return AgentContext(
        assessment_id="test-orc",
        layer="orchestration",
        sql=FakeSqlClient({"min_run_seconds": sql_rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# --- collect() ---

def test_collect_returns_two_evidence_entries():
    ev = OrcRunMonitoringCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_content():
    ev = OrcRunMonitoringCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert "120" in sql_ev.summary or "60" in sql_ev.summary
    assert sql_ev.rows[0]["total_runs"] == 120
    assert sql_ev.rows[0]["distinct_runs"] == 60
    assert sql_ev.rows[0]["avg_run_seconds"] == 300.0
    assert sql_ev.rows[0]["max_run_seconds"] == 900.0
    assert sql_ev.rows[0]["min_run_seconds"] == 180.0


def test_collect_summary_includes_duration_range():
    ev = OrcRunMonitoringCheck().collect(_ctx())
    # summary should mention avg or range
    summary = ev[0].summary
    assert "300.0" in summary or "avg" in summary


def test_collect_note_mentions_monitoring_gap():
    ev = OrcRunMonitoringCheck().collect(_ctx())
    note = ev[1]
    assert note.kind == "note"
    assert "monitor" in note.summary.lower()


def test_collect_no_runs_summary():
    ev = OrcRunMonitoringCheck().collect(_ctx(rows=[]))
    assert "No workflow runs found" in ev[0].summary
    assert ev[0].rows[0]["total_runs"] == 0


def test_collect_empty_sql_result_handled():
    ctx = AgentContext(
        assessment_id="t",
        layer="orchestration",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = OrcRunMonitoringCheck().collect(ctx)
    assert ev[0].rows[0]["total_runs"] == 0
    assert ev[0].rows[0]["avg_run_seconds"] is None


# --- judge() ---

def test_judge_met_verdict():
    f = OrcRunMonitoringCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    f = OrcRunMonitoringCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET


def test_judge_confidence_capped_at_medium():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "Some duration data available but no alerting evidence."}'
    )
    f = OrcRunMonitoringCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_sql_and_note():
    f = OrcRunMonitoringCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


# --- llm=None ---

def test_no_llm_degrades_to_unassessed():
    f = OrcRunMonitoringCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
