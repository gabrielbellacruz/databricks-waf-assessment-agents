from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.r_time_travel_recovery import TimeTravelRecoveryCheck

_Q = Question(
    id="PRO-R-04",
    pillar_id="reliability",
    title="Recover pipelines using data time travel",
    principle="Design for failure and recovery",
)

# Two distinct SQL needles:
#   "information_schema.tables"  -> _DELTA_TABLES_SQL (Delta adoption)
#   "VERSION AS OF"              -> _TIME_TRAVEL_SQL  (usage history)
_FAKE_RESPONSES = {
    "information_schema.tables": [{"total_tables": 100, "delta_tables": 90}],
    "VERSION AS OF": [
        {"restore_stmts": 2, "version_as_of_stmts": 5, "timestamp_as_of_stmts": 1}
    ],
}

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "High Delta adoption and time-travel usage confirm recovery capability."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "medium", "score": null,'
    ' "rationale": "Delta present but time-travel usage is rare."}'
)


def _ctx(*, llm_response: str | None = _LLM_MET) -> AgentContext:
    return AgentContext(
        assessment_id="test-assessment",
        layer="processing",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidence_entries():
    ev = TimeTravelRecoveryCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_delta_adoption_evidence():
    ev = TimeTravelRecoveryCheck().collect(_ctx())
    delta_ev = ev[0]
    assert delta_ev.kind == "sql"
    assert delta_ev.rows[0]["total_tables"] == 100
    assert delta_ev.rows[0]["delta_tables"] == 90
    assert "90.0%" in delta_ev.summary


def test_collect_usage_evidence():
    ev = TimeTravelRecoveryCheck().collect(_ctx())
    usage_ev = ev[1]
    assert usage_ev.kind == "sql"
    assert usage_ev.rows[0]["restore_stmts"] == 2
    assert usage_ev.rows[0]["version_as_of_stmts"] == 5
    assert "RESTORE=2" in usage_ev.summary


def test_collect_retention_note():
    ev = TimeTravelRecoveryCheck().collect(_ctx())
    note_ev = ev[2]
    assert note_ev.kind == "note"
    assert "logRetentionDuration" in note_ev.summary


def test_collect_empty_responses_handled():
    ctx = AgentContext(
        assessment_id="t2",
        layer="processing",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = TimeTravelRecoveryCheck().collect(ctx)
    assert ev[0].rows[0]["total_tables"] == 0
    assert ev[1].rows[0]["restore_stmts"] == 0


def test_judge_met_verdict():
    f = TimeTravelRecoveryCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_partial_verdict():
    f = TimeTravelRecoveryCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL


def test_judge_confidence_capped_at_medium():
    high_conf = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "strong evidence"}'
    )
    f = TimeTravelRecoveryCheck().run(_Q, _ctx(llm_response=high_conf))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_note():
    f = TimeTravelRecoveryCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert "note" in kinds


def test_no_llm_degrades_to_unassessed():
    f = TimeTravelRecoveryCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
