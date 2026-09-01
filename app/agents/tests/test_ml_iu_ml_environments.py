from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.iu_ml_environments import MlEnvironmentsCheck

_Q = Question(
    id="ML-IU-03",
    pillar_id="interoperability-usability",
    title="Provide self-service ML development environments",
    principle="Enable engineers to access ML compute independently",
)

# Needle "ml_usage_rows"  → _ML_USAGE_SQL
# Needle "ml_sku_name"    → _ML_SKU_DISTRIBUTION_SQL
_FAKE_RESPONSES = {
    "ml_usage_rows": [
        {"ml_usage_rows": 250, "workspaces_using_ml": 3, "tagged_ml_rows": 120}
    ],
    "ml_sku_name": [
        {"ml_sku_name": "JOBS_COMPUTE_ML", "sku_rows": 180},
        {"ml_sku_name": "ALL_PURPOSE_COMPUTE", "sku_rows": 70},
    ],
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
    ev = MlEnvironmentsCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert ev[2].kind == "note"


def test_collect_usage_summary_mentions_workspaces():
    ev = MlEnvironmentsCheck().collect(_ctx())
    assert "3" in ev[0].summary  # workspaces_using_ml
    assert "250" in ev[0].summary  # ml_usage_rows


def test_collect_sku_evidence_row_count():
    ev = MlEnvironmentsCheck().collect(_ctx())
    assert len(ev[1].rows) == 2


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium", "score": null,'
        ' "rationale": "Some ML compute used but not broadly"}'
    )
    f = MlEnvironmentsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_no_llm_degrades_to_unassessed():
    f = MlEnvironmentsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
