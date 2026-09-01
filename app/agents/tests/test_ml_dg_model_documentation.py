from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.dg_model_documentation import MlModelDocumentationCheck

_Q = Question(
    id="ML-DG-05",
    pillar_id="data-ai-governance",
    title="Maintain model documentation and cards",
    principle="Document ML models for discoverability and governance",
)

# Needle "tables_with_comments" → _ML_COMMENTS_SQL
# Needle "tables_with_tags"     → _ML_TAGS_SQL
_FAKE_RESPONSES = {
    "tables_with_comments": [{"total_ml_uc_tables": 15, "tables_with_comments": 10}],
    "tables_with_tags": [{"tables_with_tags": 7}],
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
    ev = MlModelDocumentationCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert ev[2].kind == "note"


def test_collect_comment_summary():
    ev = MlModelDocumentationCheck().collect(_ctx())
    assert "10" in ev[0].summary
    assert "15" in ev[0].summary


def test_collect_tags_summary():
    ev = MlModelDocumentationCheck().collect(_ctx())
    assert "7" in ev[1].summary


def test_collect_note_mentions_mlflow():
    ev = MlModelDocumentationCheck().collect(_ctx())
    assert "mlflow" in ev[2].summary.lower()


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium", "score": null,'
        ' "rationale": "Good comment and tag coverage"}'
    )
    f = MlModelDocumentationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_unknown_verdict():
    resp = (
        '{"verdict": "unknown", "confidence": "low", "score": null,'
        ' "rationale": "No docs found"}'
    )
    f = MlModelDocumentationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN


def test_no_llm_degrades_to_unassessed():
    f = MlModelDocumentationCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
