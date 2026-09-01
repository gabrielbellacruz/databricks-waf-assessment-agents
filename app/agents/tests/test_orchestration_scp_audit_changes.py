from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.scp_audit_changes import AuditChangesCheck

_Q = Question(
    id="ORC-SCP-04",
    pillar_id="scp",
    title="Audit workflow permission and definition changes",
    principle="Maintain an audit trail of all workflow definition and permission modifications",
)

# Two distinct needles for the two SQL queries in this check
_JOB_EVENTS_NEEDLE = "service_name = 'jobs'"
_PERM_EVENTS_NEEDLE = "service_name = 'permissions'"


def _ctx(
    job_events: list[dict],
    perm_total: int,
    perm_actions: int,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient(
            {
                _JOB_EVENTS_NEEDLE: job_events,
                _PERM_EVENTS_NEEDLE: [
                    {"total_perm_events": perm_total, "distinct_perm_actions": perm_actions}
                ],
            }
        ),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidence_pieces():
    ev = AuditChangesCheck().collect(
        _ctx(
            [{"action_name": "create", "event_count": 10}],
            perm_total=5,
            perm_actions=2,
        )
    )
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert ev[2].kind == "note"


def test_collect_job_events_summary_with_events():
    ev = AuditChangesCheck().collect(
        _ctx(
            [
                {"action_name": "create", "event_count": 5},
                {"action_name": "runNow", "event_count": 30},
            ],
            perm_total=2,
            perm_actions=1,
        )
    )
    assert "35 job-service audit events" in ev[0].summary
    assert "2 distinct action types" in ev[0].summary


def test_collect_no_job_events_summary():
    ev = AuditChangesCheck().collect(_ctx([], perm_total=0, perm_actions=0))
    assert "No job-service audit events" in ev[0].summary


def test_collect_perm_events_summary():
    ev = AuditChangesCheck().collect(
        _ctx(
            [{"action_name": "update", "event_count": 4}],
            perm_total=8,
            perm_actions=3,
        )
    )
    assert "8 job permission-change events" in ev[1].summary
    assert "3 distinct action types" in ev[1].summary


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Rich audit trail with multiple action types"}'
    )
    f = AuditChangesCheck().run(
        _Q,
        _ctx(
            [{"action_name": "create", "event_count": 10}],
            perm_total=5,
            perm_actions=2,
            llm_response=resp,
        ),
    )
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_unknown_verdict_no_events():
    resp = (
        '{"verdict": "unknown", "confidence": "low",'
        ' "score": null, "rationale": "No audit events found"}'
    )
    f = AuditChangesCheck().run(
        _Q, _ctx([], perm_total=0, perm_actions=0, llm_response=resp)
    )
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_no_llm_degrades_to_unassessed():
    f = AuditChangesCheck().run(
        _Q,
        _ctx(
            [{"action_name": "update", "event_count": 3}],
            perm_total=1,
            perm_actions=1,
            llm_response=None,
        ),
    )
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
