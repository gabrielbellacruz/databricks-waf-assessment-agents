from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.dg_training_lineage import MlTrainingLineageCheck

_Q = Question(
    id="ML-DG-02",
    pillar_id="data-ai-governance",
    title="Track lineage from training data to model",
    principle="Maintain full data provenance for ML",
)

# Needle "ml_lineage_targets" → _ML_TARGETS_SQL
# Needle "source_table_full_name" → _ML_EDGES_SQL
_EDGE_ROW = {
    "source_table_full_name": "main.raw.events",
    "target_table_full_name": "main.ml.features",
    "edge_events": 12,
}
_FAKE_RESPONSES = {
    "ml_lineage_targets": [{"ml_lineage_targets": 5}],
    "source_table_full_name": [_EDGE_ROW],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidence_items():
    ev = MlTrainingLineageCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert ev[2].kind == "note"


def test_collect_lineage_target_summary():
    ev = MlTrainingLineageCheck().collect(_ctx())
    assert "5" in ev[0].summary
    assert "lineage" in ev[0].summary.lower()


def test_collect_edge_rows_attached():
    ev = MlTrainingLineageCheck().collect(_ctx())
    assert ev[1].rows  # at least one edge row


def test_judge_maps_llm_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium", "score": null,'
        ' "rationale": "Lineage recorded for feature tables"}'
    )
    f = MlTrainingLineageCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_caps_high_to_medium():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "Some lineage found"}'
    )
    f = MlTrainingLineageCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = MlTrainingLineageCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
