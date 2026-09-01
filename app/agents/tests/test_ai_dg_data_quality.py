from __future__ import annotations

from waf_agents.ai.checks.dg_data_quality import AiDataQualityCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-DG-04",
    pillar_id="dg",
    title="Ensure quality of data grounding generative apps",
    principle="Ground generative AI on high-quality, validated data",
)

# Distinct needles:
#   "ai_dq_constraints" -> _CONSTRAINTS_SQL
#   "ai_dq_column_tags" -> _TAGS_SQL
_FAKE = {
    "ai_dq_constraints": [{"ai_dq_constraints": 45, "constrained_tables": 10}],
    "ai_dq_column_tags": [{"ai_dq_column_tags": 120, "tagged_tables": 30}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_reports_constraints():
    ev = AiDataQualityCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "45" in ev[0].summary
    assert "10" in ev[0].summary
    assert "constraint" in ev[0].summary.lower()


def test_collect_reports_column_tags():
    ev = AiDataQualityCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "120" in ev[1].summary
    assert "tag" in ev[1].summary.lower()


def test_collect_includes_grounding_limitation():
    ev = AiDataQualityCheck().collect(_ctx())
    assert ev[2].kind == "uc_metadata"
    assert "rag" in ev[2].summary.lower() or "ground" in ev[2].summary.lower()


def test_collect_has_three_evidence_items():
    ev = AiDataQualityCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_rows_attached():
    ev = AiDataQualityCheck().collect(_ctx())
    assert ev[0].rows[0]["ai_dq_constraints"] == 45
    assert ev[1].rows[0]["ai_dq_column_tags"] == 120


def test_collect_empty_sql_returns_zeros():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=FakeLlmClient(""),
    )
    ev = AiDataQualityCheck().collect(ctx)
    assert "0" in ev[0].summary


def test_judge_maps_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "low",'
        ' "score": null, "rationale": "Few constraints; no AI-specific quality gates"}'
    )
    f = AiDataQualityCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.LOW


def test_judge_caps_high_to_medium():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some tags and constraints but incomplete"}'
    )
    f = AiDataQualityCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = AiDataQualityCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
