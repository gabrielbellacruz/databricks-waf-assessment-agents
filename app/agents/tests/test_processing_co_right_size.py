from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.co_right_size import ProcessingRightSizeCheck

_Q = Question(
    id="PRO-CO-02",
    pillar_id="cost-optimization",
    title="Right-size compute for transformation jobs",
    principle="Optimize compute cost and efficiency",
)

# Needles are distinct, non-overlapping substrings of the two SQL strings:
#   "job_run_timeline" -> _RUNS_SQL  (FROM system.lakeflow.job_run_timeline)
#   "query.history"   -> _QUERY_SQL (FROM system.query.history)
_FAKE_RESPONSES = {
    "job_run_timeline": [{"total_runs": 100, "failed_runs": 5, "success_runs": 90}],
    "query.history": [{"total_queries": 500, "avg_task_ms": 30000.0, "max_task_ms": 120000.0}],
}


def _ctx(llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_gathers_run_and_query_evidence():
    ev = ProcessingRightSizeCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert "job runs" in ev[0].summary
    assert ev[1].kind == "sql"
    assert ev[2].kind == "note"


def test_collect_run_evidence_has_rows():
    ev = ProcessingRightSizeCheck().collect(_ctx())
    assert ev[0].rows[0]["total_runs"] == 100
    assert ev[0].rows[0]["failed_runs"] == 5


def test_collect_query_evidence_has_rows():
    ev = ProcessingRightSizeCheck().collect(_ctx())
    assert ev[1].rows[0]["total_queries"] == 500


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some jobs have high failure rates"}'
    )
    f = ProcessingRightSizeCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Low failure rate and reasonable durations"}'
    )
    f = ProcessingRightSizeCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET


def test_no_llm_degrades_to_unassessed():
    f = ProcessingRightSizeCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
