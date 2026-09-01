from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.dg_training_data_quality import MlTrainingDataQualityCheck

_Q = Question(
    id="ML-DG-04",
    pillar_id="data-ai-governance",
    title="Ensure quality of training data",
    principle="Validate and document training dataset quality",
)

# Needle "ml_check_constraints" → _ML_CHECK_CONSTRAINTS_SQL
# Needle "ml_table_constraints" → _ML_TABLE_CONSTRAINTS_SQL
# Needle "total_ml_tables"      → _ML_TOTAL_TABLES_SQL
_FAKE_RESPONSES = {
    "ml_check_constraints": [{"ml_check_constraints": 8}],
    "ml_table_constraints": [{"ml_table_constraints": 12}],
    "total_ml_tables": [{"total_ml_tables": 40}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_two_evidence_items():
    ev = MlTrainingDataQualityCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    assert ev[1].kind == "note"


def test_collect_summary_mentions_constraints():
    ev = MlTrainingDataQualityCheck().collect(_ctx())
    summary = ev[0].summary
    assert "8" in summary   # check constraints
    assert "12" in summary  # table constraints
    assert "40" in summary  # total tables


def test_collect_note_mentions_dlt():
    ev = MlTrainingDataQualityCheck().collect(_ctx())
    note_lower = ev[1].summary.lower()
    assert "dlt" in note_lower or "lakeflow" in note_lower


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium", "score": null,'
        ' "rationale": "Some constraints found"}'
    )
    f = MlTrainingDataQualityCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_high_confidence_capped():
    resp = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "Good constraint coverage"}'
    )
    f = MlTrainingDataQualityCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = MlTrainingDataQualityCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
