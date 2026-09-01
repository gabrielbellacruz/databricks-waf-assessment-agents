from __future__ import annotations

from waf_agents.ai.checks.oe_user_feedback import UserFeedbackCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-OE-05",
    pillar_id="oe",
    title="Collect and act on user feedback",
    principle="Close the loop between users and model improvement",
)

# Needles:
#   "ai_gateway.usage" -> gateway endpoint names (first query)
#   "APPS" -> billing query
#   "databricksapps" -> audit query
_FAKE = {
    "ai_gateway.usage": [
        {"endpoint_name": "chat-feedback-collector", "total_calls": 300},
        {"endpoint_name": "rag-v2", "total_calls": 1200},
    ],
    "APPS": [{"app_billing_rows": 5, "total_dbus": 12.5}],
    "databricksapps": [{"app_audit_events": 42, "distinct_actions": 3}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_gateway_feedback_heuristic():
    ev = UserFeedbackCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "2 AI Gateway endpoint" in ev[0].summary
    # "chat-feedback-collector" matches "feedback" token -> 1 feedback-named endpoint
    assert "1" in ev[0].summary


def test_collect_billing_evidence():
    ev = UserFeedbackCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "5" in ev[1].summary
    assert "12.5" in ev[1].summary


def test_collect_audit_evidence():
    ev = UserFeedbackCheck().collect(_ctx())
    assert ev[2].kind == "sql"
    assert "42" in ev[2].summary


def test_collect_note_evidence():
    ev = UserFeedbackCheck().collect(_ctx())
    assert ev[3].kind == "note"
    assert "NOT observable" in ev[3].summary


def test_collect_no_apps_billing():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({"ai_gateway.usage": [], "databricksapps": []}),
        llm=FakeLlmClient(""),
    )
    ev = UserFeedbackCheck().collect(ctx)
    billing_ev = next(e for e in ev if "billing" in e.detail.lower() or "APPS" in e.detail)
    assert "No Databricks Apps billing" in billing_ev.summary


def test_judge_unknown_thin_signal():
    resp = (
        '{"verdict": "unknown", "confidence": "low",'
        ' "score": null, "rationale": "No direct feedback mechanism observable"}'
    )
    f = UserFeedbackCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_judge_partial():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "App deployed; feedback endpoint name found"}'
    )
    f = UserFeedbackCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL


def test_no_llm_degrades_to_unassessed():
    f = UserFeedbackCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
