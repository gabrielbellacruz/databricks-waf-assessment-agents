from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.r_event_driven import OrcEventDrivenCheck

_Q = Question(
    id="ORC-R-05",
    pillar_id="reliability",
    title="React to platform events in workflows",
    principle="Automate operations to reduce human error",
)

_SQL_ROWS = [{
    "total_jobs": 20,
    "file_arrival_jobs": 6,
    "scheduled_jobs": 10,
    "continuous_jobs": 2,
}]

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "6 file-arrival and 2 continuous jobs indicate event-driven patterns."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "low", "score": null,'
    ' "rationale": "Some event-driven jobs but majority are time-scheduled."}'
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
        sql=FakeSqlClient({"file_arrival_jobs": sql_rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# --- collect() ---

def test_collect_returns_two_evidence_entries():
    ev = OrcEventDrivenCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_content():
    ev = OrcEventDrivenCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert "20" in sql_ev.summary
    assert "6" in sql_ev.summary  # file_arrival_jobs
    assert sql_ev.rows[0]["total_jobs"] == 20
    assert sql_ev.rows[0]["file_arrival_jobs"] == 6
    assert sql_ev.rows[0]["continuous_jobs"] == 2


def test_collect_summary_shows_trigger_breakdown():
    ev = OrcEventDrivenCheck().collect(_ctx())
    # summary should mention file-arrival, continuous, scheduled
    assert "file-arrival" in ev[0].summary
    assert "continuous" in ev[0].summary
    assert "scheduled" in ev[0].summary


def test_collect_note_mentions_broader_events():
    ev = OrcEventDrivenCheck().collect(_ctx())
    note = ev[1]
    assert note.kind == "note"
    assert "webhooks" in note.summary.lower() or "trigger" in note.summary.lower()


def test_collect_no_jobs_summary():
    ev = OrcEventDrivenCheck().collect(_ctx(rows=[]))
    assert "No active workflow jobs" in ev[0].summary


def test_collect_empty_sql_result_handled():
    ctx = AgentContext(
        assessment_id="t",
        layer="orchestration",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = OrcEventDrivenCheck().collect(ctx)
    assert ev[0].rows[0]["total_jobs"] == 0


# --- judge() ---

def test_judge_met_verdict():
    f = OrcEventDrivenCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_partial_verdict():
    f = OrcEventDrivenCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL


def test_judge_confidence_capped_at_medium():
    resp = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "Majority of jobs use event triggers."}'
    )
    f = OrcEventDrivenCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_sql_and_note():
    f = OrcEventDrivenCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


# --- llm=None ---

def test_no_llm_degrades_to_unassessed():
    f = OrcEventDrivenCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
