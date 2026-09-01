from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.dg_quality_expectations import (
    ProcessingQualityExpectationsCheck,
)

_Q = Question(
    id="PRO-DG-02",
    pillar_id="data-ai-governance",
    title="Enforce data quality expectations during processing",
    principle="Validate data at every transformation step",
)

# Distinct SQL needles:
#   "lakeflow.pipelines"   -> pipeline_count
#   "check_constraints"    -> check constraint count
#   "total_tables"         -> total governed tables
_FAKE_RESPONSES = {
    "lakeflow.pipelines": [{"pipeline_count": 5}],
    "check_constraints": [{"check_constraints": 12}],
    "total_tables": [{"total_tables": 80}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_includes_pipeline_and_constraint_evidence():
    ev = ProcessingQualityExpectationsCheck().collect(_ctx())
    # Three evidence items: pipeline, constraints, note
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert "5" in ev[0].summary  # pipeline_count
    assert "12" in ev[1].summary  # check_constraints


def test_collect_note_mentions_expectations():
    ev = ProcessingQualityExpectationsCheck().collect(_ctx())
    note = ev[2]
    assert note.kind == "note"
    assert "expectations" in note.summary.lower()


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some pipelines use DLT expectations"}'
    )
    f = ProcessingQualityExpectationsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "No constraints or pipelines found"}'
    )
    f = ProcessingQualityExpectationsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = ProcessingQualityExpectationsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
