from __future__ import annotations

from waf_agents.analytics.checks.dg_semantic_layer import SemanticLayerCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-DG-02",
    pillar_id="data-ai-governance",
    title="Ensure a consistent semantic layer for metrics",
    principle="Metrics should have a single authoritative definition",
)

# Needles: 'materialized_views' matches _VIEWS_SQL,
#          'semantic_schemas' matches _SEMANTIC_NAMING_SQL.
_FAKE_RESPONSES = {
    "materialized_views": [
        {"total_views": 15, "materialized_views": 5, "regular_views": 10}
    ],
    "semantic_schemas": [{"semantic_schemas": 3, "semantic_objects": 20}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_view_evidence():
    ev = SemanticLayerCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "15" in ev[0].summary
    assert "materialized" in ev[0].summary.lower()


def test_collect_returns_naming_evidence():
    ev = SemanticLayerCheck().collect(_ctx())
    assert len(ev) == 2
    assert "20" in ev[1].summary
    assert "3" in ev[1].summary


def test_collect_evidence_rows_present():
    ev = SemanticLayerCheck().collect(_ctx())
    assert ev[0].rows


def test_judge_maps_llm_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Consistent semantic layer exists"}'
    )
    f = SemanticLayerCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_high_confidence_to_medium():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some views but not consistent"}'
    )
    f = SemanticLayerCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = SemanticLayerCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
