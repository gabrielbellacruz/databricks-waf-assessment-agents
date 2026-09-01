from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.pe_join_optimization import JoinOptimizationCheck

_Q = Question(
    id="PRO-PE-02",
    pillar_id="performance-efficiency",
    title="Optimize joins in transformations",
    principle="Optimise for the native execution engine",
)

# needle "BROADCAST" -> pe_join_optimization SQL (unique to that module)
_SQL_ROWS = [
    {
        "broadcast_hints": 12,
        "skew_hints": 3,
        "merge_shuffle_hints": 2,
        "join_stmts": 80,
        "total_stmts": 600,
    }
]

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "Broadcast hints present for join optimisation."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "medium", "score": null,'
    ' "rationale": "No join optimisation hints found despite many JOIN statements."}'
)


def _ctx(*, llm_response: str | None = _LLM_MET, rows: list[dict] | None = None) -> AgentContext:
    sql_rows = _SQL_ROWS if rows is None else rows
    return AgentContext(
        assessment_id="test-assessment",
        layer="processing",
        sql=FakeSqlClient({"BROADCAST": sql_rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_two_evidence_entries():
    ev = JoinOptimizationCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_counts():
    ev = JoinOptimizationCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert sql_ev.rows[0]["broadcast_hints"] == 12
    assert sql_ev.rows[0]["skew_hints"] == 3
    assert sql_ev.rows[0]["join_stmts"] == 80


def test_collect_summary_mentions_broadcast():
    ev = JoinOptimizationCheck().collect(_ctx())
    assert "BROADCAST=12" in ev[0].summary


def test_collect_note_evidence():
    ev = JoinOptimizationCheck().collect(_ctx())
    note_ev = ev[1]
    assert note_ev.kind == "note"
    assert note_ev.rows == []
    assert "Spark UI" in note_ev.summary


def test_collect_no_history():
    ctx = AgentContext(
        assessment_id="t2",
        layer="processing",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = JoinOptimizationCheck().collect(ctx)
    assert "No query-history rows" in ev[0].summary
    assert ev[0].rows[0]["broadcast_hints"] == 0


def test_judge_met_verdict():
    f = JoinOptimizationCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict():
    f = JoinOptimizationCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET


def test_judge_confidence_capped_at_medium():
    high_conf = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "mixed signals"}'
    )
    f = JoinOptimizationCheck().run(_Q, _ctx(llm_response=high_conf))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = JoinOptimizationCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
