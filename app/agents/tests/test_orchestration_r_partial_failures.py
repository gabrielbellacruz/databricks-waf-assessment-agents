from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.r_partial_failures import OrcPartialFailuresCheck

_Q = Question(
    id="ORC-R-02",
    pillar_id="reliability",
    title="Handle partial failures without full reruns",
    principle="Design for failure and recovery",
)

_SQL_ROWS = [{"total_runs": 40, "succeeded_runs": 30, "failed_runs": 5, "skipped_runs": 5}]

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "SKIPPED states indicate run_if conditions are configured."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "low", "score": null,'
    ' "rationale": "No SKIPPED runs detected; partial failure handling unconfirmed."}'
)


def _ctx(*, llm_response: str | None = _LLM_MET, runs: list[dict] | None = None) -> AgentContext:
    sql_rows = _SQL_ROWS if runs is None else runs
    return AgentContext(
        assessment_id="test-orc",
        layer="orchestration",
        sql=FakeSqlClient({"skipped_runs": sql_rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# --- collect() ---

def test_collect_returns_two_evidence_entries():
    ev = OrcPartialFailuresCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_content():
    ev = OrcPartialFailuresCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert "40" in sql_ev.summary
    assert "5" in sql_ev.summary  # failed or skipped
    assert sql_ev.rows[0]["total_runs"] == 40
    assert sql_ev.rows[0]["skipped_runs"] == 5


def test_collect_skipped_mention_in_summary():
    ev = OrcPartialFailuresCheck().collect(_ctx())
    assert "SKIPPED" in ev[0].summary


def test_collect_note_references_run_if():
    ev = OrcPartialFailuresCheck().collect(_ctx())
    note = ev[1]
    assert note.kind == "note"
    assert "run_if" in note.summary


def test_collect_no_runs_reports_zero():
    ev = OrcPartialFailuresCheck().collect(_ctx(runs=[]))
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
    ev = OrcPartialFailuresCheck().collect(ctx)
    assert ev[0].rows[0]["skipped_runs"] == 0


# --- judge() ---

def test_judge_met_verdict():
    f = OrcPartialFailuresCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    f = OrcPartialFailuresCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET


def test_judge_confidence_capped_at_medium():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "Some partial handling in evidence."}'
    )
    f = OrcPartialFailuresCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_sql_and_note():
    f = OrcPartialFailuresCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


# --- llm=None ---

def test_no_llm_degrades_to_unassessed():
    f = OrcPartialFailuresCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
