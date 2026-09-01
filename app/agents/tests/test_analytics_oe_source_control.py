from __future__ import annotations

from waf_agents.analytics.checks.oe_source_control import AnalyticsSourceControlCheck
from waf_agents.core.clients import AgentContext, FakeArtifactClient, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-OE-01",
    pillar_id="operational-excellence",
    title="Version-control dashboards and queries",
    principle="Optimize build and release processes",
)


def _ctx(
    *,
    jobs: list[dict] | None = None,
    pipelines: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(),
        artifacts=FakeArtifactClient(jobs=jobs or [], pipelines=pipelines or []),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_counts_git_backed_job():
    job = {
        "settings": {
            "name": "dashboard_refresh",
            "git_source": {"url": "https://github.com/acme/analytics"},
        }
    }
    ev = AnalyticsSourceControlCheck().collect(_ctx(jobs=[job]))
    assert ev[0].kind == "job_config"
    assert "1 of 1" in ev[0].summary


def test_collect_non_git_job_counted_correctly():
    job = {
        "settings": {
            "name": "manual_job",
            "tasks": [
                {"notebook_task": {"notebook_path": "/Users/foo/notebook"}}
            ],
        }
    }
    ev = AnalyticsSourceControlCheck().collect(_ctx(jobs=[job]))
    assert "0 of 1" in ev[0].summary


def test_collect_repos_path_job_counts_as_git():
    job = {
        "settings": {
            "tasks": [
                {"notebook_task": {"notebook_path": "/Repos/user@example.com/analytics/dashboard"}}
            ]
        }
    }
    ev = AnalyticsSourceControlCheck().collect(_ctx(jobs=[job]))
    assert "1 of 1" in ev[0].summary


def test_collect_pipeline_git_evidence():
    pipeline = {
        "spec": {
            "libraries": [{"notebook": {"path": "/Repos/user@example.com/pipelines/etl"}}]
        }
    }
    ev = AnalyticsSourceControlCheck().collect(_ctx(pipelines=[pipeline]))
    assert ev[1].kind == "pipeline"
    assert "1 of 1" in ev[1].summary


def test_collect_no_artifacts_returns_empty():
    ctx = AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(),
        artifacts=None,
        llm=FakeLlmClient(""),
    )
    ev = AnalyticsSourceControlCheck().collect(ctx)
    assert ev == []


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some jobs use git but dashboards unchecked"}'
    )
    job = {"settings": {"name": "j1", "git_source": {}}}
    f = AnalyticsSourceControlCheck().run(_Q, _ctx(jobs=[job], llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "No git-backed jobs found"}'
    )
    f = AnalyticsSourceControlCheck().run(_Q, _ctx(jobs=[], llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_returns_unassessed_with_sources():
    job = {"settings": {"name": "j1", "git_source": {}}}
    f = AnalyticsSourceControlCheck().run(_Q, _ctx(jobs=[job], llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
