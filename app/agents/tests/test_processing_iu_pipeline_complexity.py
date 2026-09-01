from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.iu_pipeline_complexity import (
    ProcessingPipelineComplexityCheck,
)

_Q = Question(
    id="PRO-IU-01",
    pillar_id="interoperability-usability",
    title="Reduce complexity of transformation pipelines",
    principle="Design pipelines that are simple, modular, and maintainable",
)

# Distinct SQL needles:
#   "lakeflow.pipelines"               -> pipeline_count
#   "delete_time IS NULL"              -> job_count
#   "result_state IN ('FAILED', 'ERROR')"  -> run stats
_FAKE_RESPONSES = {
    "lakeflow.pipelines": [{"pipeline_count": 4}],
    "delete_time IS NULL": [{"job_count": 6}],
    "result_state IN ('FAILED', 'ERROR')": [{"total_runs": 200, "failed_runs": 10}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_workload_evidence():
    ev = ProcessingPipelineComplexityCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert "4" in ev[0].summary  # pipeline_count
    assert "6" in ev[0].summary  # job_count


def test_collect_run_evidence():
    ev = ProcessingPipelineComplexityCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "200" in ev[1].summary  # total_runs


def test_collect_note_warns_about_task_count():
    ev = ProcessingPipelineComplexityCheck().collect(_ctx())
    assert ev[2].kind == "note"
    assert "task" in ev[2].summary.lower() or "depth" in ev[2].summary.lower()


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Mix of pipelines and complex jobs"}'
    )
    f = ProcessingPipelineComplexityCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "High pipeline ratio indicates declarative paradigm"}'
    )
    f = ProcessingPipelineComplexityCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET


def test_no_llm_degrades_to_unassessed():
    f = ProcessingPipelineComplexityCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
