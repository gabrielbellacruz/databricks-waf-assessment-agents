from __future__ import annotations

from waf_agents.ai.checks.iu_governed_endpoints import AiGovernedEndpointsCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-IU-04",
    pillar_id="iu",
    title="Expose AI functionality through governed endpoints/tools",
    principle="Publish AI capabilities via governed, monitored serving endpoints",
)

# Distinct needles:
#   "governed_endpoint_requests" -> _SERVING_SQL
#   "gateway_governed_calls"     -> _GATEWAY_SQL
#   "ai_tool_routines"           -> _ROUTINES_SQL
_FAKE = {
    "governed_endpoint_requests": [
        {"governed_endpoint_requests": 3, "total_endpoint_requests": 25000}
    ],
    "gateway_governed_calls": [
        {"gateway_governed_calls": 18000, "gateway_endpoints": 3}
    ],
    "ai_tool_routines": [
        {"ai_tool_routines": 6, "ai_tool_catalogs": 2}
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_reports_serving_endpoints():
    ev = AiGovernedEndpointsCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "3" in ev[0].summary
    assert "endpoint" in ev[0].summary.lower()


def test_collect_reports_gateway_calls():
    ev = AiGovernedEndpointsCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "18000" in ev[1].summary
    assert "gateway" in ev[1].summary.lower()


def test_collect_reports_uc_tools():
    ev = AiGovernedEndpointsCheck().collect(_ctx())
    assert ev[2].kind == "sql"
    assert "6" in ev[2].summary


def test_collect_includes_governance_limitation():
    ev = AiGovernedEndpointsCheck().collect(_ctx())
    assert ev[3].kind == "uc_metadata"
    assert "acl" in ev[3].summary.lower() or "permission" in ev[3].summary.lower()


def test_collect_has_four_evidence_items():
    ev = AiGovernedEndpointsCheck().collect(_ctx())
    assert len(ev) == 4


def test_collect_rows_attached():
    ev = AiGovernedEndpointsCheck().collect(_ctx())
    assert ev[0].rows[0]["governed_endpoint_requests"] == 3
    assert ev[1].rows[0]["gateway_governed_calls"] == 18000
    assert ev[2].rows[0]["ai_tool_routines"] == 6


def test_collect_empty_sql_returns_zeros():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=FakeLlmClient(""),
    )
    ev = AiGovernedEndpointsCheck().collect(ctx)
    assert "0" in ev[0].summary


def test_judge_maps_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Endpoints active and governed via AI Gateway"}'
    )
    f = AiGovernedEndpointsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_high_to_medium():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Fully governed endpoints"}'
    )
    f = AiGovernedEndpointsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = AiGovernedEndpointsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
