from __future__ import annotations

from waf_agents.analytics.checks.iu_secure_sharing import SecureSharingAnalyticsCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-IU-05",
    pillar_id="interoperability-usability",
    title="Enable secure sharing of analytics outputs",
    principle="Analytics outputs shared externally should use controlled, auditable mechanisms",
)

# Needle: 'sharing_tables' matches _DELTASHARING_SQL (via data_source_format = 'DELTASHARING').
_FAKE_WITH_SHARING = {
    "sharing_tables": [{"sharing_tables": 8, "sharing_catalogs": 2}],
}

_FAKE_NO_SHARING = {
    "sharing_tables": [{"sharing_tables": 0, "sharing_catalogs": 0}],
}


def _ctx(responses: dict, *, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(responses),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_consumer_evidence_with_sharing():
    ev = SecureSharingAnalyticsCheck().collect(_ctx(_FAKE_WITH_SHARING))
    assert ev[0].kind == "sql"
    assert "8" in ev[0].summary
    assert "2" in ev[0].summary


def test_collect_consumer_evidence_no_sharing():
    ev = SecureSharingAnalyticsCheck().collect(_ctx(_FAKE_NO_SHARING))
    assert "0" in ev[0].summary


def test_collect_limitation_evidence():
    ev = SecureSharingAnalyticsCheck().collect(_ctx(_FAKE_WITH_SHARING))
    assert len(ev) == 2
    assert ev[1].kind == "uc_metadata"
    assert "provider" in ev[1].summary.lower()


def test_judge_met_when_sharing_active():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Delta Sharing in use for analytics outputs"}'
    )
    f = SecureSharingAnalyticsCheck().run(_Q, _ctx(_FAKE_WITH_SHARING, llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_no_sharing():
    resp = (
        '{"verdict": "not_met", "confidence": "low",'
        ' "score": null, "rationale": "No Delta Sharing consumer tables detected"}'
    )
    f = SecureSharingAnalyticsCheck().run(_Q, _ctx(_FAKE_NO_SHARING, llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = SecureSharingAnalyticsCheck().run(_Q, _ctx(_FAKE_WITH_SHARING, llm_response=None))
    assert f.auto_assessable is False
    assert f.sources
