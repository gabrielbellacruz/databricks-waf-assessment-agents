from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeArtifactClient, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.oe_workflows_as_code import OrcWorkflowsAsCodeCheck

_Q = Question(
    id="ORC-OE-02",
    pillar_id="oe",
    title="Define workflows as code with CI/CD",
    principle="Manage workflow definitions in source control with automated deployment pipelines",
)

_GIT_JOB = {
    "settings": {
        "name": "etl-pipeline",
        "git_source": {"git_url": "https://github.com/org/repo", "git_branch": "main"},
        "tasks": [],
    }
}

_NOTEBOOK_JOB = {
    "settings": {
        "name": "ad-hoc-notebook",
        "tasks": [
            {"notebook_task": {"notebook_path": "/Users/alice@example.com/notebook"}}
        ],
    }
}

_REPOS_JOB = {
    "settings": {
        "name": "repos-backed",
        "tasks": [
            {"notebook_task": {"notebook_path": "/Repos/alice@example.com/my-repo/notebook"}}
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


def test_collect_counts_git_jobs():
    ev = OrcWorkflowsAsCodeCheck().collect(_ctx([_GIT_JOB, _NOTEBOOK_JOB, _REPOS_JOB]))
    assert ev[0].kind == "job_config"
    assert "2 of 3 jobs" in ev[0].summary


def test_collect_includes_note_evidence():
    ev = OrcWorkflowsAsCodeCheck().collect(_ctx([_GIT_JOB]))
    assert len(ev) == 2
    assert ev[1].kind == "note"


def test_collect_sample_rows_include_git_backed_flag():
    ev = OrcWorkflowsAsCodeCheck().collect(_ctx([_GIT_JOB, _NOTEBOOK_JOB]))
    rows = ev[0].rows
    names = {r["name"] for r in rows}
    assert "etl-pipeline" in names
    git_backed = {r["name"]: r["git_backed"] for r in rows}
    assert git_backed["etl-pipeline"] is True
    assert git_backed["ad-hoc-notebook"] is False


def test_collect_no_artifacts_returns_note():
    ctx = AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient(),
        artifacts=None,
        llm=FakeLlmClient(""),
    )
    ev = OrcWorkflowsAsCodeCheck().collect(ctx)
    assert ev[0].kind == "note"


def test_judge_maps_llm_verdict_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some jobs use Git source but not all"}'
    )
    f = OrcWorkflowsAsCodeCheck().run(_Q, _ctx([_GIT_JOB, _NOTEBOOK_JOB], llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "No jobs use Git source"}'
    )
    f = OrcWorkflowsAsCodeCheck().run(_Q, _ctx([_NOTEBOOK_JOB], llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = OrcWorkflowsAsCodeCheck().run(_Q, _ctx([_GIT_JOB], llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
