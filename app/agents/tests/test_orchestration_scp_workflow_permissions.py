from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.scp_workflow_permissions import WorkflowPermissionsCheck

_Q = Question(
    id="ORC-SCP-02",
    pillar_id="scp",
    title="Scope workflow permissions to only required resources",
    principle="Apply least-privilege to workflow service principals and job ACLs",
)

# Two distinct needles for the two SQL queries
_IDENTITIES_NEEDLE = "COUNT(DISTINCT run_as)"
_PERM_NEEDLE = "service_name = 'permissions'"


def _ctx(
    total_jobs: int,
    distinct_ids: int,
    sp_jobs: int,
    perm_events: int,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient(
            {
                _IDENTITIES_NEEDLE: [
                    {
                        "total_jobs": total_jobs,
                        "distinct_identities": distinct_ids,
                        "sp_jobs": sp_jobs,
                    }
                ],
                _PERM_NEEDLE: [{"perm_change_events": perm_events}],
            }
        ),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidence_pieces():
    ev = WorkflowPermissionsCheck().collect(_ctx(50, 5, 45, 10))
    assert len(ev) == 3
    kinds = [e.kind for e in ev]
    assert kinds == ["sql", "sql", "note"]


def test_collect_identity_summary():
    ev = WorkflowPermissionsCheck().collect(_ctx(50, 5, 45, 10))
    assert "5 distinct run_as identities" in ev[0].summary
    assert "50 jobs" in ev[0].summary


def test_collect_perm_events_summary():
    ev = WorkflowPermissionsCheck().collect(_ctx(50, 5, 45, 12))
    assert "12 job permission-change events" in ev[1].summary


def test_collect_no_jobs():
    ev = WorkflowPermissionsCheck().collect(_ctx(0, 0, 0, 0))
    assert "No jobs found" in ev[0].summary


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Multiple SPs but some overlap prod/non-prod"}'
    )
    f = WorkflowPermissionsCheck().run(_Q, _ctx(50, 5, 45, 3, llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Granular SPs per workflow"}'
    )
    f = WorkflowPermissionsCheck().run(_Q, _ctx(20, 20, 20, 5, llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = WorkflowPermissionsCheck().run(_Q, _ctx(10, 2, 9, 1, llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
