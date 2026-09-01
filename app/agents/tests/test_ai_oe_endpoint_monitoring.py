from __future__ import annotations

from waf_agents.ai.checks.oe_endpoint_monitoring import EndpointMonitoringCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-OE-03",
    pillar_id="oe",
    title="Monitor AI endpoints for quality, latency, and drift",
    principle="Maintain visibility into AI system health",
)

# Needle for endpoint_health SQL: "total_execution_time_ms" is in _ENDPOINT_HEALTH_SQL
# Needle for gateway_status SQL: "guardrail_request_blocked" is in _GATEWAY_STATUS_SQL
_FAKE = {
    "total_execution_time_ms": [
        {
            "endpoint_name": "chat-v1",
            "total_requests": 5000,
            "error_requests": 50,
            "total_exec_ms": 2500000,
        }
    ],
    "guardrail_request_blocked": [
        {"total_calls": 4800, "error_calls": 48, "guardrail_blocked": 12}
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_endpoint_evidence_has_error_rate():
    ev = EndpointMonitoringCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "1 AI endpoint" in ev[0].summary
    assert "5000" in ev[0].summary
    assert "50" in ev[0].summary


def test_collect_gateway_evidence():
    ev = EndpointMonitoringCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "4800" in ev[1].summary
    assert "48" in ev[1].summary
    assert "12" in ev[1].summary


def test_collect_note_records_limitations():
    ev = EndpointMonitoringCheck().collect(_ctx())
    assert ev[2].kind == "note"
    assert "NOT" in ev[2].summary or "not observable" in ev[2].summary.lower()


def test_collect_no_endpoints_returns_absent_summary():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        llm=FakeLlmClient(""),
    )
    ev = EndpointMonitoringCheck().collect(ctx)
    assert "No rows" in ev[0].summary or "no active" in ev[0].summary.lower()


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Metrics visible but no alert config confirmed"}'
    )
    f = EndpointMonitoringCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Low error rate observed"}'
    )
    f = EndpointMonitoringCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = EndpointMonitoringCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
