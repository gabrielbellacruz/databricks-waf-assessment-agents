from __future__ import annotations

from waf_agents.core.clients import (
    AgentContext,
    FakeArtifactClient,
    FakeLlmClient,
    FakeSqlClient,
)
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.source_control import SourceControlCheck

_Q = Question(
    id="ING-OE-03",
    pillar_id="operational-excellence",
    title="Manage ingestion pipeline code in source control with CI/CD",
    principle="Optimize build and release processes",
)

_JOBS = [
    {"job_id": 1, "settings": {"name": "git-job", "git_source": {"git_url": "https://github/x"}}},
    {
        "job_id": 2,
        "settings": {
            "name": "repo-job",
            "tasks": [{"notebook_task": {"notebook_path": "/Repos/team/etl/land"}}],
        },
    },
    {
        "job_id": 3,
        "settings": {
            "name": "adhoc-job",
            "tasks": [{"notebook_task": {"notebook_path": "/Workspace/Users/a/nb"}}],
        },
    },
]


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient(),
        catalogs=["main"],
        artifacts=FakeArtifactClient(jobs=_JOBS, pipelines=[]),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_counts_git_backed_jobs():
    ev = SourceControlCheck().collect(_ctx())
    # first evidence line summarizes job git coverage: 2 of 3
    assert "2 of 3 jobs" in ev[0].summary
    assert ev[0].kind == "job_config"


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = '{"verdict": "partial", "confidence": "high", "score": null, "rationale": "2/3 in Git"}'
    f = SourceControlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources  # evidence attached for explainability


def test_no_llm_degrades_to_unassessed():
    f = SourceControlCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached
