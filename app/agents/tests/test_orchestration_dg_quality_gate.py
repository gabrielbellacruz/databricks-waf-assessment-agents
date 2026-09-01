"""Tests for QualityGateCheck (ORC-DG-05)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.dg_quality_gate import QualityGateCheck

_Q = Question(
    id="ORC-DG-05",
    pillar_id="data-ai-governance",
    title="Gate workflow progression on data quality",
    principle="Downstream workflow steps must not proceed past bad data",
)

# Needles are distinct substrings of the two SQL strings:
#   "CONSTRAINT"       -> _SQL_DQ_HISTORY (contains "CONSTRAINT")
#   "dlt_pipelines"    -> _SQL_PIPELINES (AS dlt_pipelines)
_FAKE_RESPONSES = {
    "CONSTRAINT": [{"dq_statements": 15}],
    "dlt_pipelines": [{"dlt_pipelines": 5}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="test-orc-dg-05",
        layer="orchestration",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidences():
    ev = QualityGateCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_dq_evidence_is_sql():
    ev = QualityGateCheck().collect(_ctx())
    assert ev[0].kind == "sql"


def test_collect_pipelines_evidence_is_sql():
    ev = QualityGateCheck().collect(_ctx())
    assert ev[1].kind == "sql"


def test_collect_note_evidence():
    ev = QualityGateCheck().collect(_ctx())
    assert ev[2].kind == "note"


def test_collect_dq_summary_reflects_count():
    ev = QualityGateCheck().collect(_ctx())
    assert "15" in ev[0].summary


def test_collect_pipeline_summary_reflects_count():
    ev = QualityGateCheck().collect(_ctx())
    assert "5" in ev[1].summary


def test_collect_rows_carry_data():
    ev = QualityGateCheck().collect(_ctx())
    assert ev[0].rows[0]["dq_statements"] == 15
    assert ev[1].rows[0]["dlt_pipelines"] == 5


def test_judge_maps_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Some DQ checks exist but not all paths gated"}'
    )
    f = QualityGateCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "DLT expectations cover all pipelines"}'
    )
    f = QualityGateCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = QualityGateCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
