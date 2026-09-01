from __future__ import annotations

from waf_agents.ai.checks.scp_content_safety import ContentSafetyCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-SCP-04",
    pillar_id="scp",
    title="Meet compliance and content-safety requirements",
    principle="Ensure AI outputs comply with safety and regulatory standards",
)

# Needles:
#   "guardrail_active_calls" appears in _SAFETY_COVERAGE_SQL as a column alias
#   "FOUNDATION_MODEL" appears in _AI_SPEND_SQL sku_name filter
_FAKE = {
    "guardrail_active_calls": [
        {
            "total_calls": 5000,
            "guardrail_active_calls": 120,
            "endpoints_with_guardrails": 4,
        }
    ],
    "FOUNDATION_MODEL": [
        {"sku_name": "FOUNDATION_MODEL_TRAINING", "total_dbus": 85.3},
        {"sku_name": "INFERENCE", "total_dbus": 42.1},
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_safety_evidence():
    ev = ContentSafetyCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "5000" in ev[0].summary
    assert "120" in ev[0].summary
    assert "4" in ev[0].summary  # endpoints_with_guardrails


def test_collect_spend_evidence():
    ev = ContentSafetyCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    # 85.3 + 42.1 = 127.4 total DBUs
    assert "127.4" in ev[1].summary or "2 AI" in ev[1].summary


def test_collect_note_evidence():
    ev = ContentSafetyCheck().collect(_ctx())
    assert ev[2].kind == "note"
    assert "NOT" in ev[2].summary or "not exposed" in ev[2].summary.lower()


def test_collect_no_guardrail_activity():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        llm=FakeLlmClient(""),
    )
    ev = ContentSafetyCheck().collect(ctx)
    assert "No" in ev[0].summary


def test_judge_partial():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Some guardrails active; categories unconfirmed"}'
    )
    f = ContentSafetyCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_unknown_no_gateway():
    resp = (
        '{"verdict": "unknown", "confidence": "low",'
        ' "score": null, "rationale": "No guardrail signals observed"}'
    )
    f = ContentSafetyCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_no_llm_degrades_to_unassessed():
    f = ContentSafetyCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
