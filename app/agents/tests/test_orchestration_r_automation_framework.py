from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.r_automation_framework import OrcAutomationFrameworkCheck

_Q = Question(
    id="ORC-R-03",
    pillar_id="reliability",
    title="Use a job automation framework with built-in recovery",
    principle="Automate operations to reduce human error",
)

# Distinct needles for the two SQL queries:
#   "active_jobs"    → _SQL_JOBS
#   "succeeded_runs" → _SQL_RUNS
_FAKE = {
    "active_jobs": [{"active_jobs": 15}],
    "succeeded_runs": [{"total_runs": 60, "succeeded_runs": 50, "failed_runs": 10}],
}

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "15 active jobs found; Databricks Workflows is in use."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "low", "score": null,'
    ' "rationale": "No active jobs; no automation framework detected."}'
)


def _ctx(
    *,
    llm_response: str | None = _LLM_MET,
    fake: dict | None = None,
) -> AgentContext:
    return AgentContext(
        assessment_id="test-orc",
        layer="orchestration",
        sql=FakeSqlClient(fake if fake is not None else dict(_FAKE)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# --- collect() ---

def test_collect_returns_three_evidence_entries():
    ev = OrcAutomationFrameworkCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_jobs_evidence_content():
    ev = OrcAutomationFrameworkCheck().collect(_ctx())
    ev_jobs = ev[0]
    assert ev_jobs.kind == "sql"
    assert "15" in ev_jobs.summary
    assert ev_jobs.rows[0]["active_jobs"] == 15


def test_collect_runs_evidence_content():
    ev = OrcAutomationFrameworkCheck().collect(_ctx())
    ev_runs = ev[1]
    assert ev_runs.kind == "sql"
    assert "60" in ev_runs.summary
    assert ev_runs.rows[0]["total_runs"] == 60
    assert ev_runs.rows[0]["succeeded_runs"] == 50


def test_collect_note_mentions_recovery_gap():
    ev = OrcAutomationFrameworkCheck().collect(_ctx())
    note = ev[2]
    assert note.kind == "note"
    assert "recovery" in note.summary.lower()


def test_collect_no_jobs_shows_not_detected():
    ctx = _ctx(fake={"active_jobs": [{"active_jobs": 0}], "succeeded_runs": []})
    ev = OrcAutomationFrameworkCheck().collect(ctx)
    assert "not detected" in ev[0].summary


def test_collect_empty_sql_result_handled():
    ctx = AgentContext(
        assessment_id="t",
        layer="orchestration",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = OrcAutomationFrameworkCheck().collect(ctx)
    assert ev[0].rows[0]["active_jobs"] == 0
    assert ev[1].rows[0]["total_runs"] == 0


# --- judge() ---

def test_judge_met_verdict():
    f = OrcAutomationFrameworkCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    f = OrcAutomationFrameworkCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET


def test_judge_confidence_capped_at_medium():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "Some jobs use automation but recovery not confirmed."}'
    )
    f = OrcAutomationFrameworkCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_jobs_runs_and_note():
    f = OrcAutomationFrameworkCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert kinds.count("sql") == 2
    assert "note" in kinds


# --- llm=None ---

def test_no_llm_degrades_to_unassessed():
    f = OrcAutomationFrameworkCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
