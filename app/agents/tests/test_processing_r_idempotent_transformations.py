from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.r_idempotent_transformations import IdempotentTransformationsCheck

_Q = Question(
    id="PRO-R-02",
    pillar_id="reliability",
    title="Make transformations idempotent",
    principle="Design for failure and recovery",
)

# needle "MERGE INTO" -> r_idempotent_transformations SQL (unique to that module)
_SQL_ROWS = [
    {
        "merge_into_stmts": 30,
        "replace_where_stmts": 10,
        "insert_overwrite_stmts": 5,
        "insert_into_stmts": 20,
        "total_stmts": 500,
    }
]

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "Predominant use of MERGE INTO and REPLACE WHERE indicates idempotent writes."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "medium", "score": null,'
    ' "rationale": "Mix of idempotent and non-idempotent patterns observed."}'
)


def _ctx(*, llm_response: str | None = _LLM_MET, rows: list[dict] | None = None) -> AgentContext:
    sql_rows = _SQL_ROWS if rows is None else rows
    return AgentContext(
        assessment_id="test-assessment",
        layer="processing",
        sql=FakeSqlClient({"MERGE INTO": sql_rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_two_evidence_entries():
    ev = IdempotentTransformationsCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_counts():
    ev = IdempotentTransformationsCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert sql_ev.rows[0]["merge_into_stmts"] == 30
    assert sql_ev.rows[0]["replace_where_stmts"] == 10
    assert sql_ev.rows[0]["insert_overwrite_stmts"] == 5
    assert sql_ev.rows[0]["insert_into_stmts"] == 20


def test_collect_sql_summary_mentions_idempotent_writes():
    ev = IdempotentTransformationsCheck().collect(_ctx())
    assert "idempotent" in ev[0].summary.lower()


def test_collect_note_evidence():
    ev = IdempotentTransformationsCheck().collect(_ctx())
    note_ev = ev[1]
    assert note_ev.kind == "note"
    assert note_ev.rows == []
    assert "idempotency" in note_ev.summary.lower() or "idempotent" in note_ev.summary.lower()


def test_collect_no_history_shows_zero():
    ctx = AgentContext(
        assessment_id="t2",
        layer="processing",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = IdempotentTransformationsCheck().collect(ctx)
    assert ev[0].rows[0]["total_stmts"] == 0
    assert "No query-history rows" in ev[0].summary


def test_judge_met_verdict():
    f = IdempotentTransformationsCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_partial_verdict():
    f = IdempotentTransformationsCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL


def test_judge_confidence_capped_at_medium():
    high_conf = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "strong evidence"}'
    )
    f = IdempotentTransformationsCheck().run(_Q, _ctx(llm_response=high_conf))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_sql_and_note():
    f = IdempotentTransformationsCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


def test_no_llm_degrades_to_unassessed():
    f = IdempotentTransformationsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
