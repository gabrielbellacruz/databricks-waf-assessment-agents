from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeArtifactClient, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.oe_task_dependencies import TaskDependenciesCheck

_Q = Question(
    id="ORC-OE-03",
    pillar_id="oe",
    title="Model task dependencies explicitly",
    principle="Declare explicit task dependencies for correct execution order",
)

_SINGLE_TASK_JOB = {
    "settings": {
        "name": "single-task",
        "tasks": [{"task_key": "ingest"}],
    }
}

_MULTI_WITH_DEPS = {
    "settings": {
        "name": "multi-dep",
        "tasks": [
            {"task_key": "extract"},
            {"task_key": "transform", "depends_on": [{"task_key": "extract"}]},
            {"task_key": "load", "depends_on": [{"task_key": "transform"}]},
        ],
    }
}

_MULTI_NO_DEPS = {
    "settings": {
        "name": "multi-no-dep",
        "tasks": [
            {"task_key": "task_a"},
            {"task_key": "task_b"},
        ],
    }
}


def _ctx(jobs: list[dict], llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient(),
        artifacts=FakeArtifactClient(jobs=jobs),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_counts_multi_task_jobs_with_deps():
    ev = TaskDependenciesCheck().collect(
        _ctx([_SINGLE_TASK_JOB, _MULTI_WITH_DEPS, _MULTI_NO_DEPS])
    )
    assert ev[0].kind == "job_config"
    # 1 of 2 multi-task jobs has deps; 1 single-task excluded
    assert "1 of 2 multi-task jobs" in ev[0].summary


def test_collect_includes_note():
    ev = TaskDependenciesCheck().collect(_ctx([_MULTI_WITH_DEPS]))
    assert len(ev) == 2
    assert ev[1].kind == "note"


def test_collect_sample_rows_flag_deps():
    ev = TaskDependenciesCheck().collect(_ctx([_MULTI_WITH_DEPS, _MULTI_NO_DEPS]))
    rows = ev[0].rows
    assert any(r["name"] == "multi-dep" and r["explicit_deps"] is True for r in rows)
    assert any(r["name"] == "multi-no-dep" and r["explicit_deps"] is False for r in rows)


def test_collect_no_artifacts_returns_note():
    ctx = AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient(),
        artifacts=None,
        llm=FakeLlmClient(""),
    )
    ev = TaskDependenciesCheck().collect(ctx)
    assert ev[0].kind == "note"


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "All multi-task jobs have explicit depends_on"}'
    )
    f = TaskDependenciesCheck().run(_Q, _ctx([_MULTI_WITH_DEPS], llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Dependencies explicit"}'
    )
    f = TaskDependenciesCheck().run(_Q, _ctx([_MULTI_WITH_DEPS], llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = TaskDependenciesCheck().run(_Q, _ctx([_MULTI_WITH_DEPS], llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
