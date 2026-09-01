from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.dg_access_control import MlAccessControlCheck

_Q = Question(
    id="ML-DG-03",
    pillar_id="data-ai-governance",
    title="Control access to models, features, and training data",
    principle="Least-privilege access for ML artifacts",
)

# Needle "total_ml_grants" → _ML_GRANTS_SQL
# Needle "total_ml_uc_tables" → _ML_TABLES_COVERAGE_SQL
_FAKE_RESPONSES = {
    "total_ml_grants": [{"total_ml_grants": 30, "user_grants": 5, "group_grants": 25}],
    "total_ml_uc_tables": [{"total_ml_uc_tables": 20, "ml_tables_with_grants": 18}],
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
    ev = MlAccessControlCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert ev[2].kind == "note"


def test_collect_grant_summary_mentions_counts():
    ev = MlAccessControlCheck().collect(_ctx())
    summary = ev[0].summary
    assert "30" in summary  # total_ml_grants
    assert "25" in summary  # group_grants


def test_collect_coverage_summary_mentions_tables():
    ev = MlAccessControlCheck().collect(_ctx())
    assert "18" in ev[1].summary
    assert "20" in ev[1].summary


def test_judge_maps_llm_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium", "score": null,'
        ' "rationale": "Group-based grants dominate"}'
    )
    f = MlAccessControlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met():
    resp = (
        '{"verdict": "not_met", "confidence": "low", "score": null,'
        ' "rationale": "Mostly user grants found"}'
    )
    f = MlAccessControlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = MlAccessControlCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
