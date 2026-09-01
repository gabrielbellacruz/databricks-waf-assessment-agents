from __future__ import annotations

from waf_agents.ai.checks.iu_serverless_serving import AiServerlessServingCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-IU-05",
    pillar_id="iu",
    title="Use serverless model serving",
    principle="Use serverless compute for model serving to simplify operations",
)

# Distinct needles:
#   "serverless_serving_dbus" -> _BILLING_SQL
#   "fmapi_gateway_calls"     -> _GATEWAY_SQL
_FAKE = {
    "serverless_serving_dbus": [
        {
            "serverless_serving_dbus": 50.0,
            "provisioned_serving_dbus": 0.0,
            "fmapi_serving_dbus": 200.0,
        }
    ],
    "fmapi_gateway_calls": [{"fmapi_gateway_calls": 3000, "fmapi_gateway_endpoints": 2}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_reports_billing_split():
    ev = AiServerlessServingCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "50.00" in ev[0].summary
    assert "200.00" in ev[0].summary
    assert "serverless" in ev[0].summary.lower()


def test_collect_reports_gateway_calls():
    ev = AiServerlessServingCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "3000" in ev[1].summary
    assert "serverless" in ev[1].summary.lower() or "gateway" in ev[1].summary.lower()


def test_collect_includes_serverless_limitation():
    ev = AiServerlessServingCheck().collect(_ctx())
    assert ev[2].kind == "uc_metadata"
    assert "serverless" in ev[2].summary.lower()


def test_collect_has_three_evidence_items():
    ev = AiServerlessServingCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_rows_attached():
    ev = AiServerlessServingCheck().collect(_ctx())
    assert ev[0].rows[0]["serverless_serving_dbus"] == 50.0
    assert ev[1].rows[0]["fmapi_gateway_calls"] == 3000


def test_collect_empty_sql_returns_zeros():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=FakeLlmClient(""),
    )
    ev = AiServerlessServingCheck().collect(ctx)
    assert "0.00" in ev[0].summary


def test_judge_maps_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Serverless and FMAPI DBUs present, no provisioned"}'
    )
    f = AiServerlessServingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_maps_partial_verdict_when_mixed():
    resp = (
        '{"verdict": "partial", "confidence": "low",'
        ' "score": null, "rationale": "Mix of serverless and provisioned endpoints detected"}'
    )
    f = AiServerlessServingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.LOW


def test_judge_caps_high_to_medium():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "All serving is serverless"}'
    )
    f = AiServerlessServingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = AiServerlessServingCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
