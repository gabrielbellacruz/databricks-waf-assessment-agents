from __future__ import annotations

from waf_agents.ai.checks.scp_endpoint_access import EndpointAccessCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-SCP-03",
    pillar_id="scp",
    title="Scope AI endpoint access and credentials",
    principle="Apply least-privilege to AI endpoint access",
)

# Needles:
#   "Permission" appears in _PERM_EVENTS_SQL action_name filter
#   "distinct_requesters" appears in _REQUESTER_BREADTH_SQL as a column alias
_FAKE = {
    "Permission": [
        {"action_name": "grantServingEndpointPermission", "event_count": 4},
        {"action_name": "revokeServingEndpointPermission", "event_count": 2},
    ],
    "distinct_requesters": [
        {"endpoint_name": "chat-v1", "distinct_requesters": 3, "total_calls": 1500},
        {"endpoint_name": "embeddings-prod", "distinct_requesters": 7, "total_calls": 900},
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_permission_events_summary():
    ev = EndpointAccessCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    # 4 + 2 = 6 total events
    assert "6" in ev[0].summary
    assert "2" in ev[0].summary  # distinct action types


def test_collect_requester_breadth():
    ev = EndpointAccessCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    # max distinct requesters = 7
    assert "7" in ev[1].summary


def test_collect_note_evidence():
    ev = EndpointAccessCheck().collect(_ctx())
    assert ev[2].kind == "note"
    assert "REST API" in ev[2].summary or "NOT" in ev[2].summary


def test_collect_no_perm_events():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        llm=FakeLlmClient(""),
    )
    ev = EndpointAccessCheck().collect(ctx)
    assert "No serving-endpoint permission" in ev[0].summary


def test_judge_partial():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Some permission management but broad requester count"}'
    )
    f = EndpointAccessCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_capped():
    resp = (
        '{"verdict": "not_met", "confidence": "high",'
        ' "score": null, "rationale": "No scoping evidence"}'
    )
    f = EndpointAccessCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = EndpointAccessCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
