from __future__ import annotations

from waf_agents.ai.checks.scp_prompt_injection import PromptInjectionCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-SCP-02",
    pillar_id="scp",
    title="Defend against prompt injection and misuse",
    principle="Protect AI systems from adversarial prompt attacks",
)

# Needles:
#   "guardrail_request_blocked" in _GUARDRAIL_BLOCK_SQL
#   "client_error_requests" in _ENDPOINT_ERRORS_SQL (column alias)
_FAKE = {
    "guardrail_request_blocked": [
        {
            "total_calls": 3000,
            "request_blocked": 25,
            "response_blocked": 5,
            "client_errors": 60,
        }
    ],
    "client_error_requests": [
        {"total_requests": 2500, "client_error_requests": 50}
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_guardrail_block_summary():
    ev = PromptInjectionCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "3000" in ev[0].summary
    assert "25" in ev[0].summary  # request_blocked
    assert "60" in ev[0].summary  # client_errors


def test_collect_endpoint_error_evidence():
    ev = PromptInjectionCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "2500" in ev[1].summary
    assert "50" in ev[1].summary


def test_collect_note_records_limits():
    ev = PromptInjectionCheck().collect(_ctx())
    assert ev[2].kind == "note"
    assert "semantic" in ev[2].summary.lower() or "NOT" in ev[2].summary


def test_collect_no_gateway():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        llm=FakeLlmClient(""),
    )
    ev = PromptInjectionCheck().collect(ctx)
    assert "No" in ev[0].summary


def test_judge_partial():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Guardrails active but direct traffic not covered"}'
    )
    f = PromptInjectionCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met():
    resp = (
        '{"verdict": "not_met", "confidence": "low",'
        ' "score": null, "rationale": "No guardrail blocking observed"}'
    )
    f = PromptInjectionCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.LOW


def test_no_llm_degrades_to_unassessed():
    f = PromptInjectionCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
