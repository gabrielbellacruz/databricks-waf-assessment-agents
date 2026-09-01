from __future__ import annotations

from waf_agents.core.clients import (
    AgentContext,
    FakeArtifactClient,
    FakeLlmClient,
    FakeSqlClient,
)
from waf_agents.core.models import Question, Verdict
from waf_agents.processing.checks.oe_declarative_pipelines import DeclarativePipelinesCheck

_Q = Question(
    id="PRO-OE-05",
    pillar_id="operational-excellence",
    title="Use declarative management for complex pipelines",
    principle="Manage complex transformation pipelines declaratively with DLT or DABs",
)


def _ctx(
    pipelines: int = 3,
    jobs: int = 5,
    artifact_pipelines: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient({
            "lakeflow.pipelines": [{"n": pipelines}],
            "lakeflow.jobs": [{"n": jobs}],
        }),
        catalogs=["main"],
        artifacts=FakeArtifactClient(pipelines=artifact_pipelines or []),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_count_evidence():
    ev = DeclarativePipelinesCheck().collect(_ctx(pipelines=4, jobs=6))
    assert ev[0].kind == "sql"
    assert "4" in ev[0].summary
    assert "6" in ev[0].summary


def test_collect_artifact_pipeline_evidence():
    artifact_pipelines = [
        {"spec": {"name": "complex-etl", "libraries": [{"notebook": {"path": "/n1"}},
                                                        {"notebook": {"path": "/n2"}}],
                  "continuous": True}}
    ]
    ev = DeclarativePipelinesCheck().collect(_ctx(artifact_pipelines=artifact_pipelines))
    # Should have count_evidence, pipeline_evidence, note_evidence
    assert len(ev) == 3
    assert ev[1].kind == "pipeline"
    assert ev[1].rows[0]["library_count"] == 2
    assert ev[1].rows[0]["continuous"] is True


def test_collect_note_always_present():
    ev = DeclarativePipelinesCheck().collect(_ctx())
    note = next((e for e in ev if e.kind == "note"), None)
    assert note is not None
    assert "DAB" in note.summary or "bundle" in note.summary.lower()


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Multiple DLT pipelines with multi-library configs"}'
    )
    f = DeclarativePipelinesCheck().run(_Q, _ctx(pipelines=5, jobs=2, llm_response=resp))
    assert f.verdict is Verdict.MET


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "low",'
        ' "score": null, "rationale": "No DLT pipelines found; all workloads are plain jobs"}'
    )
    f = DeclarativePipelinesCheck().run(_Q, _ctx(pipelines=0, jobs=10, llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = DeclarativePipelinesCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
