from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.r_retries_timeouts import OrcRetriesTimeoutsCheck

_Q = Question(
    id="ORC-R-01",
    pillar_id="reliability",
    title="Configure task retries and job timeouts",
    principle="Design for failure and recovery",
)

_SQL_ROWS = [{"total_runs": 50, "timed_out_runs": 8, "failed_runs": 4}]

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "TIMED_OUT runs observed; timeouts appear configured."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "medium", "score": null,'
    ' "rationale": "No TIMED_OUT runs; timeout/retry config not confirmed."}'
)


def _ctx(*, llm_response: str | None = _LLM_MET, runs: list[dict] | None = None) -> AgentContext:
    sql_rows = _SQL_ROWS if runs is None else runs
    return AgentContext(
        assessment_id="test-orc",
        layer="orchestration",
        sql=FakeSqlClient({"timed_out_runs": sql_rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# --- collect() ---

def test_collect_returns_two_evidence_entries():
    ev = OrcRetriesTimeoutsCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_content():
    ev = OrcRetriesTimeoutsCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert "50" in sql_ev.summary
    assert "8" in sql_ev.summary
    assert "4" in sql_ev.summary
    assert sql_ev.rows[0]["total_runs"] == 50
    assert sql_ev.rows[0]["timed_out_runs"] == 8
    assert sql_ev.rows[0]["failed_runs"] == 4


def test_collect_note_evidence_kind_and_limitation():
    ev = OrcRetriesTimeoutsCheck().collect(_ctx())
    note = ev[1]
    assert note.kind == "note"
    assert note.rows == []
    assert "Jobs-API" in note.summary


def test_collect_no_runs_reports_zero_and_no_runs_message():
    ev = OrcRetriesTimeoutsCheck().collect(_ctx(runs=[]))
    assert ev[0].rows[0]["total_runs"] == 0
    assert "No workflow job runs found" in ev[0].summary


def test_collect_empty_sql_result_handled():
    ctx = AgentContext(
        assessment_id="t",
        layer="orchestration",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = OrcRetriesTimeoutsCheck().collect(ctx)
    assert ev[0].rows[0]["total_runs"] == 0


# --- judge() ---

def test_judge_met_verdict():
    f = OrcRetriesTimeoutsCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict():
    f = OrcRetriesTimeoutsCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_confidence_capped_at_medium_when_llm_claims_high():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "Some evidence of timeouts."}'
    )
    f = OrcRetriesTimeoutsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_sql_and_note():
    f = OrcRetriesTimeoutsCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


# --- llm=None ---

def test_no_llm_degrades_to_unassessed():
    f = OrcRetriesTimeoutsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
