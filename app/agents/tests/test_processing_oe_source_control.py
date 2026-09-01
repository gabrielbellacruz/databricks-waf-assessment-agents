from __future__ import annotations

from waf_agents.core.clients import (
    AgentContext,
    FakeArtifactClient,
    FakeLlmClient,
    FakeSqlClient,
)
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.oe_source_control import SourceControlCheck

_Q = Question(
    id="PRO-OE-02",
    pillar_id="operational-excellence",
    title="Version and CI/CD transformation code",
    principle="Manage transformation code in source control with CI/CD",
)


def _ctx(
    jobs: list[dict] | None = None,
    pipelines: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient(),
        catalogs=["main"],
        artifacts=FakeArtifactClient(jobs=jobs or [], pipelines=pipelines or []),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_git_backed_job():
    jobs = [{"settings": {"name": "etl-job", "git_source": {"url": "https://github.com/x"}}}]
    ev = SourceControlCheck().collect(_ctx(jobs=jobs))
    assert ev[0].kind == "job_config"
    assert "1 of 1" in ev[0].summary


def test_collect_no_git_job():
    jobs = [{"settings": {"name": "adhoc-job", "tasks": []}}]
    ev = SourceControlCheck().collect(_ctx(jobs=jobs))
    assert "0 of 1" in ev[0].summary


def test_collect_repos_path_job():
    jobs = [{"settings": {"tasks": [
        {"notebook_task": {"notebook_path": "/Repos/user/project/transform"}}
    ]}}]
    ev = SourceControlCheck().collect(_ctx(jobs=jobs))
    assert "1 of 1" in ev[0].summary


def test_collect_returns_empty_when_no_artifacts():
    ctx = AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient(),
        catalogs=["main"],
        artifacts=None,
        llm=FakeLlmClient(""),
    )
    ev = SourceControlCheck().collect(ctx)
    assert ev == []


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some jobs use git, others do not"}'
    )
    jobs = [{"settings": {"git_source": {"url": "https://github.com/x"}}}]
    f = SourceControlCheck().run(_Q, _ctx(jobs=jobs, llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM  # capped from high


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "No jobs are git-backed"}'
    )
    f = SourceControlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = SourceControlCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
