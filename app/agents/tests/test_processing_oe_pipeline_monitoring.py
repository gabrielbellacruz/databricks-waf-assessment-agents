from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.oe_pipeline_monitoring import PipelineMonitoringCheck

_Q = Question(
    id="PRO-OE-03",
    pillar_id="operational-excellence",
    title="Monitor pipeline runs and data freshness",
    principle="Detect and alert on transformation failures and stale data",
)


def _ctx(total_runs: int, failed_runs: int, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient({
            "job_run_timeline": [{"total_runs": total_runs, "failed_runs": failed_runs}],
        }),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_shows_failure_rate():
    ev = PipelineMonitoringCheck().collect(_ctx(100, 10))
    assert ev[0].kind == "sql"
    assert "10 of 100" in ev[0].summary
    assert "10.0%" in ev[0].summary


def test_collect_no_runs_summary():
    ev = PipelineMonitoringCheck().collect(_ctx(0, 0))
    assert "No job runs" in ev[0].summary


def test_collect_returns_note_evidence():
    ev = PipelineMonitoringCheck().collect(_ctx(50, 5))
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "alert" in ev[1].summary.lower()


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Low failure rate suggests monitoring is in place"}'
    )
    f = PipelineMonitoringCheck().run(_Q, _ctx(100, 2, llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "High failure rate with no evidence of alerts"}'
    )
    f = PipelineMonitoringCheck().run(_Q, _ctx(100, 40, llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = PipelineMonitoringCheck().run(_Q, _ctx(50, 5, llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached
