from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.r_retries_timeouts import ProcessingRetriesTimeoutsCheck

_Q = Question(
    id="PRO-R-01",
    pillar_id="reliability",
    title="Configure retries and timeouts for processing jobs",
    principle="Design for failure and recovery",
)

_SQL_ROWS = [{"total_runs": 20, "timed_out_runs": 5, "failed_runs": 3}]

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "Timeouts observed; retries cannot be confirmed via system tables."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "medium", "score": null,'
    ' "rationale": "No TIMED_OUT runs; retry config unverifiable."}'
)


def _ctx(*, llm_response: str | None = _LLM_MET, runs: list[dict] | None = None) -> AgentContext:
    sql_rows = _SQL_ROWS if runs is None else runs
    return AgentContext(
        assessment_id="test-assessment",
        layer="processing",
        sql=FakeSqlClient({"job_run_timeline": sql_rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_two_evidence_entries():
    ev = ProcessingRetriesTimeoutsCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_content():
    ev = ProcessingRetriesTimeoutsCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert "20" in sql_ev.summary
    assert "5" in sql_ev.summary
    assert "3" in sql_ev.summary
    assert sql_ev.rows[0]["total_runs"] == 20
    assert sql_ev.rows[0]["timed_out_runs"] == 5
    assert sql_ev.rows[0]["failed_runs"] == 3


def test_collect_note_evidence():
    ev = ProcessingRetriesTimeoutsCheck().collect(_ctx())
    note_ev = ev[1]
    assert note_ev.kind == "note"
    assert note_ev.rows == []
    assert note_ev.ref == "https://docs.databricks.com/en/jobs/settings.html"


def test_collect_note_mentions_jobs_api():
    ev = ProcessingRetriesTimeoutsCheck().collect(_ctx())
    assert "Jobs-API" in ev[1].summary


def test_collect_no_runs_reports_zero():
    ev = ProcessingRetriesTimeoutsCheck().collect(_ctx(runs=[]))
    assert ev[0].rows[0]["total_runs"] == 0
    assert ev[0].rows[0]["timed_out_runs"] == 0
    assert ev[0].rows[0]["failed_runs"] == 0
    assert "No job runs found" in ev[0].summary


def test_judge_met_verdict():
    f = ProcessingRetriesTimeoutsCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict():
    f = ProcessingRetriesTimeoutsCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_confidence_capped_at_medium():
    high_conf = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "some evidence"}'
    )
    f = ProcessingRetriesTimeoutsCheck().run(_Q, _ctx(llm_response=high_conf))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_both_kinds():
    f = ProcessingRetriesTimeoutsCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


def test_no_llm_degrades_to_unassessed():
    f = ProcessingRetriesTimeoutsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
