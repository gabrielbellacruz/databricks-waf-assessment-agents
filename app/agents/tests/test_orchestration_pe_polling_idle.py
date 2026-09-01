from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.pe_polling_idle import OrcPollingIdleCheck

_Q = Question(
    id="ORC-PE-05",
    pillar_id="performance-efficiency",
    title="Avoid unnecessary polling and idle waits",
    principle="Optimize performance through efficient task design",
)

# Distinct needles:
#   "max_run_seconds"        → _SQL_DURATION
#   "status_poll_statements" → _SQL_POLL_HISTORY
_FAKE = {
    "max_run_seconds": [{"total_runs": 50, "avg_run_seconds": 600.0, "max_run_seconds": 7200.0}],
    "status_poll_statements": [{"status_poll_statements": 12}],
}

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "Low manual poll count; Workflows built-in waiting appears in use."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "low", "score": null,'
    ' "rationale": "Some manual polling detected in query history."}'
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
    ev = OrcPollingIdleCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_duration_evidence_content():
    ev = OrcPollingIdleCheck().collect(_ctx())
    ev_dur = ev[0]
    assert ev_dur.kind == "sql"
    assert "50" in ev_dur.summary
    assert ev_dur.rows[0]["total_runs"] == 50
    assert ev_dur.rows[0]["max_run_seconds"] == 7200.0


def test_collect_poll_history_evidence_content():
    ev = OrcPollingIdleCheck().collect(_ctx())
    ev_poll = ev[1]
    assert ev_poll.kind == "sql"
    assert "12" in ev_poll.summary
    assert ev_poll.rows[0]["status_poll_statements"] == 12


def test_collect_poll_summary_mentions_anti_pattern():
    ev = OrcPollingIdleCheck().collect(_ctx())
    assert "anti-pattern" in ev[1].summary or "poll" in ev[1].summary.lower()


def test_collect_note_mentions_sleep_limitation():
    ev = OrcPollingIdleCheck().collect(_ctx())
    note = ev[2]
    assert note.kind == "note"
    assert "sleep" in note.summary.lower() or "polling" in note.summary.lower()


def test_collect_empty_sql_result_handled():
    ctx = AgentContext(
        assessment_id="t",
        layer="orchestration",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = OrcPollingIdleCheck().collect(ctx)
    assert ev[0].rows[0]["total_runs"] == 0
    assert ev[1].rows[0]["status_poll_statements"] == 0


# --- judge() ---

def test_judge_met_verdict():
    f = OrcPollingIdleCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_partial_verdict():
    f = OrcPollingIdleCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL


def test_judge_confidence_capped_at_medium():
    resp = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "No polling detected."}'
    )
    f = OrcPollingIdleCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_two_sql_and_note():
    f = OrcPollingIdleCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert kinds.count("sql") == 2
    assert "note" in kinds


# --- llm=None ---

def test_no_llm_degrades_to_unassessed():
    f = OrcPollingIdleCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
