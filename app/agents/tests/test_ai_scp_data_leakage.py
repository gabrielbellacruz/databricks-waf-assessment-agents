from __future__ import annotations

from waf_agents.ai.checks.scp_data_leakage import DataLeakageCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-SCP-01",
    pillar_id="scp",
    title="Prevent sensitive data leakage in prompts/responses",
    principle="Protect sensitive information in AI interactions",
)

# Needles (system.ai_gateway.usage exposes no PII/guardrail flags; the gateway
# query now reports call volume, distinct endpoint coverage, and error count):
#   "ai_gateway.usage" -> _GUARDRAIL_PII_SQL
#   "direct_requests"  -> _DIRECT_ENDPOINT_SQL (column alias; now joins served_entities)
_FAKE = {
    "ai_gateway.usage": [
        {
            "total_calls": 2000,
            "gateway_endpoints": 5,
            "error_calls": 18,
        }
    ],
    "direct_requests": [{"direct_endpoints": 2, "direct_requests": 800}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_guardrail_evidence():
    ev = DataLeakageCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "2000" in ev[0].summary   # total gateway calls (governed-routing coverage)
    assert "5" in ev[0].summary      # distinct endpoints (per-request PII flags not exposed)
    assert "18" in ev[0].summary     # status-code errors


def test_collect_direct_endpoint_evidence():
    ev = DataLeakageCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "800" in ev[1].summary or "2" in ev[1].summary


def test_collect_note_evidence():
    ev = DataLeakageCheck().collect(_ctx())
    assert ev[2].kind == "note"
    assert "bypass" in ev[2].summary.lower() or "NOT" in ev[2].summary


def test_collect_no_gateway_traffic():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        llm=FakeLlmClient(""),
    )
    ev = DataLeakageCheck().collect(ctx)
    assert "No" in ev[0].summary


def test_judge_partial():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "PII guardrails active but direct traffic bypasses"}'
    )
    f = DataLeakageCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "No guardrail evidence; all traffic direct"}'
    )
    f = DataLeakageCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = DataLeakageCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
