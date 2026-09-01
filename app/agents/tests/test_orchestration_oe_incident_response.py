from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.oe_incident_response import IncidentResponseCheck

_Q = Question(
    id="ORC-OE-05",
    pillar_id="oe",
    title="Define an incident response process for workflow failures",
    principle="Have a documented process to detect, triage and remediate workflow failures",
)

# Two distinct needles for the two SQL queries in this check
_FAILURES_NEEDLE = "job_run_timeline"
_RERUNS_NEEDLE = "action_name = 'runNow'"


def _ctx(
    total_runs: int,
    failed_runs: int,
    manual_runs: int,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient(
            {
                _FAILURES_NEEDLE: [{"total_runs": total_runs, "failed_runs": failed_runs}],
                _RERUNS_NEEDLE: [{"manual_run_events": manual_runs}],
            }
        ),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidence_pieces():
    ev = IncidentResponseCheck().collect(_ctx(100, 10, 5))
    assert len(ev) == 3
    assert ev[0].kind == "sql"   # failures
    assert ev[1].kind == "sql"   # manual reruns
    assert ev[2].kind == "note"


def test_collect_failure_summary():
    ev = IncidentResponseCheck().collect(_ctx(100, 15, 3))
    assert "15 of 100" in ev[0].summary
    assert "15.0%" in ev[0].summary


def test_collect_rerun_summary():
    ev = IncidentResponseCheck().collect(_ctx(100, 5, 7))
    assert "7 manual runNow events" in ev[1].summary


def test_collect_note_mentions_process():
    ev = IncidentResponseCheck().collect(_ctx(50, 5, 2))
    assert "incident-response" in ev[2].summary.lower() or "incident" in ev[2].summary.lower()


def test_collect_no_runs():
    ev = IncidentResponseCheck().collect(_ctx(0, 0, 0))
    assert "No job runs found" in ev[0].summary


def test_judge_unknown_verdict_with_llm():
    resp = (
        '{"verdict": "unknown", "confidence": "low",'
        ' "score": null, "rationale": "Insufficient signal to assess incident response process"}'
    )
    f = IncidentResponseCheck().run(_Q, _ctx(100, 10, 5, llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Some manual re-runs observed after failures"}'
    )
    f = IncidentResponseCheck().run(_Q, _ctx(100, 20, 15, llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = IncidentResponseCheck().run(_Q, _ctx(100, 10, 5, llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert len(f.sources) == 3
