from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.oe_monitoring import OrcMonitoringCheck

_Q = Question(
    id="ORC-OE-04",
    pillar_id="oe",
    title="Monitor workflows and alert on failure/SLA breach",
    principle="Detect and respond to workflow failures and SLA breaches automatically",
)

_SQL_NEEDLE = "job_run_timeline"


def _ctx(total: int, failed: int, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient(
            {_SQL_NEEDLE: [{"total_runs": total, "failed_runs": failed}]}
        ),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_calculates_failure_pct():
    ev = OrcMonitoringCheck().collect(_ctx(200, 10))
    assert ev[0].kind == "sql"
    assert "10 of 200" in ev[0].summary
    assert "5.0%" in ev[0].summary


def test_collect_includes_alert_note():
    ev = OrcMonitoringCheck().collect(_ctx(100, 5))
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "alert" in ev[1].summary.lower()


def test_collect_no_runs_summary():
    ev = OrcMonitoringCheck().collect(_ctx(0, 0))
    assert "No job runs found" in ev[0].summary


def test_collect_evidence_rows():
    ev = OrcMonitoringCheck().collect(_ctx(100, 20))
    row = ev[0].rows[0]
    assert row["total_runs"] == 100
    assert row["failed_runs"] == 20
    assert row["failure_pct"] == 20.0


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Low failure rate and alerts configured"}'
    )
    f = OrcMonitoringCheck().run(_Q, _ctx(100, 2, llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "High failure rate, no evidence of alerting"}'
    )
    f = OrcMonitoringCheck().run(_Q, _ctx(100, 60, llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = OrcMonitoringCheck().run(_Q, _ctx(100, 10, llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
