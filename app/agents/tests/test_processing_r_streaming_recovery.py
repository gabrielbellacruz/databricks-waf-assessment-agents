from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.r_streaming_recovery import StreamingRecoveryCheck

_Q = Question(
    id="PRO-R-03",
    pillar_id="reliability",
    title="Recover streaming transformations from failures",
    principle="Design for failure and recovery",
)

# needle "checkpointLocation" -> r_streaming_recovery SQL (90-day window)
_SQL_ROWS = [{"checkpoint_stmts": 15, "streaming_stmts": 40, "total_stmts": 800}]

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "checkpointLocation usage confirms streams are restartable."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "medium", "score": null,'
    ' "rationale": "Some streams use checkpoints; others may not."}'
)


def _ctx(*, llm_response: str | None = _LLM_MET, rows: list[dict] | None = None) -> AgentContext:
    sql_rows = _SQL_ROWS if rows is None else rows
    return AgentContext(
        assessment_id="test-assessment",
        layer="processing",
        sql=FakeSqlClient({"checkpointLocation": sql_rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_two_evidence_entries():
    ev = StreamingRecoveryCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_counts():
    ev = StreamingRecoveryCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert sql_ev.rows[0]["checkpoint_stmts"] == 15
    assert sql_ev.rows[0]["streaming_stmts"] == 40
    assert sql_ev.rows[0]["total_stmts"] == 800


def test_collect_summary_mentions_checkpoint():
    ev = StreamingRecoveryCheck().collect(_ctx())
    assert "checkpointLocation" in ev[0].summary


def test_collect_note_evidence():
    ev = StreamingRecoveryCheck().collect(_ctx())
    note_ev = ev[1]
    assert note_ev.kind == "note"
    assert note_ev.rows == []
    assert "Manual confirmation" in note_ev.summary


def test_collect_no_history_shows_message():
    ctx = AgentContext(
        assessment_id="t2",
        layer="processing",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = StreamingRecoveryCheck().collect(ctx)
    assert "No query-history rows" in ev[0].summary
    assert ev[0].rows[0]["checkpoint_stmts"] == 0


def test_judge_met_verdict():
    f = StreamingRecoveryCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_partial_verdict():
    f = StreamingRecoveryCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL


def test_judge_confidence_capped_at_medium():
    high_conf = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "strong evidence"}'
    )
    f = StreamingRecoveryCheck().run(_Q, _ctx(llm_response=high_conf))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_sql_and_note():
    f = StreamingRecoveryCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


def test_no_llm_degrades_to_unassessed():
    f = StreamingRecoveryCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
