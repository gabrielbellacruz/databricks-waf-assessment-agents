from __future__ import annotations

from waf_agents.core.clients import (
    AgentContext,
    FakeArtifactClient,
    FakeLlmClient,
    FakeSqlClient,
)
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.oe_deploy_code import MlDeployCodeCheck

_Q = Question(
    id="ML-OE-03",
    pillar_id="operational-excellence",
    title="Follow the deploy-code approach for ML",
    principle="Manage ML code in source control with CI/CD",
)

_GIT_JOB = {
    "settings": {
        "name": "ml-train-git",
        "git_source": {"git_url": "https://github.com/org/ml-repo"},
        "tasks": [],
    }
}
_NOTEBOOK_JOB = {
    "settings": {
        "name": "ml-train-notebook",
        "tasks": [
            {
                "notebook_task": {
                    "notebook_path": "/Users/alice/ml_training"
                }
            }
        ],
    }
}
_REPO_JOB = {
    "settings": {
        "name": "ml-train-repo",
        "tasks": [
            {
                "notebook_task": {
                    "notebook_path": "/Repos/alice@example.com/ml_project/train"
                }
            }
        ],
    }
}

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "All ML jobs sourced from Git or Repos."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "medium", "score": null,'
    ' "rationale": "Mix of Git and workspace-local notebooks."}'
)


def _ctx(
    *,
    jobs: list[dict] | None = None,
    pipelines: list[dict] | None = None,
    llm_response: str | None = _LLM_MET,
    artifacts: bool = True,
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient({}),
        catalogs=["main"],
        artifacts=(
            FakeArtifactClient(
                jobs=jobs if jobs is not None else [_GIT_JOB, _REPO_JOB],
                pipelines=pipelines or [],
            )
            if artifacts
            else None
        ),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_three_entries_with_artifacts():
    ev = MlDeployCodeCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_jobs_evidence_counts_git_backed():
    ev = MlDeployCodeCheck().collect(_ctx(jobs=[_GIT_JOB, _REPO_JOB, _NOTEBOOK_JOB]))
    assert ev[0].kind == "job_config"
    assert "2 of 3" in ev[0].summary


def test_collect_no_artifacts_returns_single_note():
    ev = MlDeployCodeCheck().collect(_ctx(artifacts=False))
    assert len(ev) == 1
    assert ev[0].kind == "note"
    assert "No artifact client" in ev[0].summary


def test_collect_note_mentions_dabs():
    ev = MlDeployCodeCheck().collect(_ctx())
    note = ev[2]
    assert note.kind == "note"
    assert "DABs" in note.summary or "bundle" in note.summary.lower()


def test_collect_pipeline_evidence_present():
    ev = MlDeployCodeCheck().collect(_ctx())
    assert ev[1].kind == "pipeline"


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_met_verdict():
    f = MlDeployCodeCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_partial_verdict():
    f = MlDeployCodeCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL


def test_judge_confidence_capped_at_medium():
    resp = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "All in Git."}'
    )
    f = MlDeployCodeCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_attached():
    f = MlDeployCodeCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.sources


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = MlDeployCodeCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
