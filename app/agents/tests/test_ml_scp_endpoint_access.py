from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.scp_endpoint_access import EndpointAccessCheck

_Q = Question(
    id="ML-SCP-04",
    pillar_id="security-compliance-privacy",
    title="Control access to model endpoints",
    principle="Apply least-privilege to model serving endpoints",
)

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "Active permission management events found for all endpoints."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "medium", "score": null,'
    ' "rationale": "Some endpoints have permission changes but others do not."}'
)


def _ctx(
    *,
    llm_response: str | None = _LLM_MET,
    perm_rows: list[dict] | None = None,
    usage_rows: list[dict] | None = None,
) -> AgentContext:
    sql_resp: dict[str, list[dict]] = {}
    # Needle for _PERM_EVENTS_SQL — "ServingEndpoint" in action_name
    sql_resp["ServingEndpoint"] = perm_rows if perm_rows is not None else [
        {"action_name": "updateServingEndpointPermissions", "event_count": 8}
    ]
    # Needle for _ENDPOINT_USAGE_SQL — "active_endpoints" column
    sql_resp["active_endpoints"] = usage_rows if usage_rows is not None else [
        {"active_endpoints": 4, "total_requests": 12000}
    ]
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(sql_resp),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_three_entries():
    ev = EndpointAccessCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_perm_evidence_shows_event_count():
    ev = EndpointAccessCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "8" in ev[0].summary  # event count
    assert "1" in ev[0].summary  # 1 distinct action type


def test_collect_usage_evidence_shows_endpoints():
    ev = EndpointAccessCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "4" in ev[1].summary   # active_endpoints
    assert "12000" in ev[1].summary  # total_requests
    assert ev[1].rows[0]["active_endpoints"] == 4


def test_collect_note_evidence_mentions_acl():
    ev = EndpointAccessCheck().collect(_ctx())
    note = ev[2]
    assert note.kind == "note"
    assert "ACL" in note.summary or "CAN_QUERY" in note.summary


def test_collect_no_perm_events_produces_safe_summary():
    ctx = AgentContext(
        assessment_id="t2",
        layer="ml",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = EndpointAccessCheck().collect(ctx)
    assert "No serving endpoint permission-change events" in ev[0].summary


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_met_verdict():
    f = EndpointAccessCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_partial_verdict():
    f = EndpointAccessCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL


def test_judge_confidence_capped_at_medium():
    resp = (
        '{"verdict": "not_met", "confidence": "high", "score": null,'
        ' "rationale": "No permission events."}'
    )
    f = EndpointAccessCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_attached():
    f = EndpointAccessCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.sources


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = EndpointAccessCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
