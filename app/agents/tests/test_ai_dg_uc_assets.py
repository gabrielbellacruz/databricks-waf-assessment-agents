from __future__ import annotations

from waf_agents.ai.checks.dg_uc_assets import UcAiAssetsCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-DG-01",
    pillar_id="dg",
    title="Govern AI assets alongside data in Unity Catalog",
    principle="Manage AI assets with the same governance as data assets",
)

# Distinct needles for each SQL:
#   "uc_routines"       -> _ROUTINES_SQL
#   "uc_asset_endpoints" -> _ENDPOINTS_SQL
_FAKE = {
    "uc_routines": [{"uc_routines": 12, "routine_catalogs": 3}],
    "uc_asset_endpoints": [{"uc_asset_endpoints": 5}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_reports_routines():
    ev = UcAiAssetsCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "12" in ev[0].summary
    assert "routine" in ev[0].summary.lower()


def test_collect_reports_endpoints():
    ev = UcAiAssetsCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "5" in ev[1].summary
    assert "endpoint" in ev[1].summary.lower()


def test_collect_includes_model_limitation():
    ev = UcAiAssetsCheck().collect(_ctx())
    assert ev[2].kind == "uc_metadata"
    assert "registered model" in ev[2].summary.lower() or "uc registered" in ev[2].summary.lower()


def test_collect_has_three_evidence_items():
    ev = UcAiAssetsCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_rows_attached():
    ev = UcAiAssetsCheck().collect(_ctx())
    assert ev[0].rows[0]["uc_routines"] == 12
    assert ev[1].rows[0]["uc_asset_endpoints"] == 5


def test_judge_maps_llm_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Some UC functions but models not visible"}'
    )
    f = UcAiAssetsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_caps_high_confidence_to_medium():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Many UC functions registered"}'
    )
    f = UcAiAssetsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = UcAiAssetsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
