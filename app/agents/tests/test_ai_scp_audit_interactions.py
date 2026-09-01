from __future__ import annotations

from waf_agents.ai.checks.scp_audit_interactions import AuditInteractionsCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-SCP-05",
    pillar_id="scp",
    title="Audit AI interactions",
    principle="Maintain an auditable record of AI system use",
)

# Needles:
#   "total_logged_calls" in _GATEWAY_AUDIT_SQL (column alias)
#   "queryServingEndpoint" in _SERVING_AUDIT_SQL action_name filter
_FAKE = {
    "total_logged_calls": [
        {
            "total_logged_calls": 4200,
            "distinct_endpoints": 5,
            "distinct_requesters": 12,
            "earliest_log": "2026-07-22",
            "latest_log": "2026-08-21",
        }
    ],
    "queryServingEndpoint": [
        {"action_name": "queryServingEndpoint", "event_count": 3800},
        {"action_name": "invokeServingEndpoint", "event_count": 200},
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_gateway_audit_summary():
    ev = AuditInteractionsCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "4200" in ev[0].summary
    assert "5" in ev[0].summary   # distinct_endpoints
    assert "12" in ev[0].summary  # distinct_requesters


def test_collect_serving_audit_summary():
    ev = AuditInteractionsCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    # 3800 + 200 = 4000 total serving events
    assert "4000" in ev[1].summary
    assert "2" in ev[1].summary  # 2 distinct action types


def test_collect_note_evidence():
    ev = AuditInteractionsCheck().collect(_ctx())
    assert ev[2].kind == "note"
    assert "retention" in ev[2].summary.lower() or "review" in ev[2].summary.lower()


def test_collect_no_gateway_logs():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        llm=FakeLlmClient(""),
    )
    ev = AuditInteractionsCheck().collect(ctx)
    assert "No" in ev[0].summary or "absent" in ev[0].summary.lower()


def test_judge_met():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "AI Gateway logging active for all traffic"}'
    )
    f = AuditInteractionsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_partial():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Gateway logs present but direct traffic less detailed"}'
    )
    f = AuditInteractionsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "All interactions logged"}'
    )
    f = AuditInteractionsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = AuditInteractionsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
