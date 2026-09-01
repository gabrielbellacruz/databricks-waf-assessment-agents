from __future__ import annotations

from waf_agents.analytics.checks.scp_sso_auth import SsoAuthCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-SCP-01",
    pillar_id="security-compliance-privacy",
    title="Authenticate analytics users via SSO",
    principle="Manage identity and access using least privilege",
)

# Needle: "action_name" -> _LOGIN_SQL (WHERE action_name IN (...) GROUP BY action_name)


def _ctx(
    *,
    login_rows: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient({"action_name": login_rows or []}),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_calculates_sso_percentage():
    rows = [
        {"action_name": "samlLogin", "event_count": 90},
        {"action_name": "passwordLogin", "event_count": 10},
    ]
    ev = SsoAuthCheck().collect(_ctx(login_rows=rows))
    assert ev[0].kind == "sql"
    assert "90 of 100" in ev[0].summary
    assert "90.0%" in ev[0].summary


def test_collect_oidc_counts_as_sso():
    rows = [{"action_name": "oidcLogin", "event_count": 50}]
    ev = SsoAuthCheck().collect(_ctx(login_rows=rows))
    assert "50 of 50" in ev[0].summary


def test_collect_no_sso_logins_shows_zero():
    rows = [{"action_name": "passwordLogin", "event_count": 50}]
    ev = SsoAuthCheck().collect(_ctx(login_rows=rows))
    assert "0 of 50" in ev[0].summary


def test_collect_empty_shows_no_events_message():
    ev = SsoAuthCheck().collect(_ctx(login_rows=[]))
    assert "No login audit events" in ev[0].summary


def test_collect_includes_note_evidence():
    ev = SsoAuthCheck().collect(_ctx())
    kinds = [e.kind for e in ev]
    assert "note" in kinds


def test_collect_evidence_has_rows():
    rows = [
        {"action_name": "samlLogin", "event_count": 40},
        {"action_name": "tokenLogin", "event_count": 5},
    ]
    ev = SsoAuthCheck().collect(_ctx(login_rows=rows))
    assert len(ev[0].rows) == 2


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "All logins via SAML SSO"}'
    )
    rows = [{"action_name": "samlLogin", "event_count": 100}]
    f = SsoAuthCheck().run(_Q, _ctx(login_rows=rows, llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Mix of SSO and password logins"}'
    )
    f = SsoAuthCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_returns_unassessed_with_sources():
    f = SsoAuthCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
