from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.iu_consistent_compute import MlConsistentComputeCheck

_Q = Question(
    id="ML-IU-05",
    pillar_id="interoperability-usability",
    title="Use consistent, pre-defined compute for ML",
    principle="Standardise ML compute via cluster policies",
)

# Needle "ml_compute_sku"    → _ML_SKU_DIST_SQL
# Needle "distinct_policies" → _POLICY_ADOPTION_SQL
_FAKE_RESPONSES = {
    "ml_compute_sku": [
        {"ml_compute_sku": "JOBS_COMPUTE_ML", "sku_count": 200},
        {"ml_compute_sku": "ALL_PURPOSE_COMPUTE", "sku_count": 50},
    ],
    "distinct_policies": [{"total_ml_rows": 250, "distinct_policies": 180}],
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
    ev = MlConsistentComputeCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert ev[2].kind == "note"


def test_collect_sku_distribution_summary():
    ev = MlConsistentComputeCheck().collect(_ctx())
    assert "2" in ev[0].summary  # 2 distinct SKU types


def test_collect_policy_summary_mentions_counts():
    ev = MlConsistentComputeCheck().collect(_ctx())
    assert "180" in ev[1].summary
    assert "250" in ev[1].summary


def test_collect_note_mentions_policies():
    ev = MlConsistentComputeCheck().collect(_ctx())
    assert "polic" in ev[2].summary.lower()


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium", "score": null,'
        ' "rationale": "High policy adoption"}'
    )
    f = MlConsistentComputeCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "low", "score": null,'
        ' "rationale": "No policies detected"}'
    )
    f = MlConsistentComputeCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = MlConsistentComputeCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
