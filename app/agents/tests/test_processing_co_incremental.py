from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.co_incremental import ProcessingIncrementalCheck

_Q = Question(
    id="PRO-CO-04",
    pillar_id="cost-optimization",
    title="Prefer incremental over full-reprocessing",
    principle="Minimize compute waste through incremental processing",
)

# Needle is a distinct substring of _SQL: "query.history"
_FAKE_RESPONSES = {
    "query.history": [{
        "merge_stmts": 30,
        "apply_changes": 10,
        "foreach_batch": 5,
        "full_reprocess": 8,
        "total": 500,
    }],
}


def _ctx(llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_counts_incremental_patterns():
    ev = ProcessingIncrementalCheck().collect(_ctx())
    assert "merge=30" in ev[0].summary
    assert "apply_changes=10" in ev[0].summary
    assert "foreachBatch=5" in ev[0].summary


def test_collect_counts_full_reprocess():
    ev = ProcessingIncrementalCheck().collect(_ctx())
    assert "full-reprocess anti-patterns=8" in ev[0].summary


def test_collect_evidence_has_rows():
    ev = ProcessingIncrementalCheck().collect(_ctx())
    assert ev[0].rows[0]["merge_stmts"] == 30
    assert ev[0].rows[0]["full_reprocess"] == 8


def test_collect_empty_query_history():
    ctx = AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient({}),
        catalogs=["main"],
        llm=FakeLlmClient(""),
    )
    ev = ProcessingIncrementalCheck().collect(ctx)
    assert "No query-history" in ev[0].summary
    assert ev[0].rows == []


def test_judge_maps_llm_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Mostly incremental patterns observed"}'
    )
    f = ProcessingIncrementalCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "low",'
        ' "score": null, "rationale": "Dominated by full-reprocess anti-patterns"}'
    )
    f = ProcessingIncrementalCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = ProcessingIncrementalCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
