from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.pe_caching_usage import CachingUsageCheck

_Q = Question(
    id="PRO-PE-03",
    pillar_id="performance-efficiency",
    title="Use caching where transformations reuse data",
    principle="Optimise for the native execution engine",
)

# needle "CACHE TABLE" -> pe_caching_usage SQL (unique to that module)
_SQL_ROWS = [{"cache_stmts": 8, "total_stmts": 300}]

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "Explicit caching patterns observed in transformation workloads."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "medium", "score": null,'
    ' "rationale": "Some caching present but coverage may be incomplete."}'
)


def _ctx(*, llm_response: str | None = _LLM_MET, rows: list[dict] | None = None) -> AgentContext:
    sql_rows = _SQL_ROWS if rows is None else rows
    return AgentContext(
        assessment_id="test-assessment",
        layer="processing",
        sql=FakeSqlClient({"CACHE TABLE": sql_rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_two_evidence_entries():
    ev = CachingUsageCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_counts():
    ev = CachingUsageCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert sql_ev.rows[0]["cache_stmts"] == 8
    assert sql_ev.rows[0]["total_stmts"] == 300


def test_collect_summary_mentions_percentage():
    ev = CachingUsageCheck().collect(_ctx())
    # 8 / 300 ≈ 2.7%
    assert "2.7%" in ev[0].summary


def test_collect_note_evidence():
    ev = CachingUsageCheck().collect(_ctx())
    note_ev = ev[1]
    assert note_ev.kind == "note"
    assert note_ev.rows == []
    assert "Delta caching" in note_ev.summary or "disk-level" in note_ev.summary


def test_collect_no_history():
    ctx = AgentContext(
        assessment_id="t2",
        layer="processing",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = CachingUsageCheck().collect(ctx)
    assert "No query-history rows" in ev[0].summary
    assert ev[0].rows[0]["cache_stmts"] == 0


def test_judge_met_verdict():
    f = CachingUsageCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_partial_verdict():
    f = CachingUsageCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL


def test_judge_confidence_capped_at_medium():
    high_conf = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "strong evidence"}'
    )
    f = CachingUsageCheck().run(_Q, _ctx(llm_response=high_conf))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = CachingUsageCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
