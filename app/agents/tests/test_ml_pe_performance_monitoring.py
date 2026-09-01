from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Question, Verdict
from waf_agents.ml.checks.pe_performance_monitoring import MlPerformanceMonitoringCheck

_Q = Question(
    id="ML-PE-05",
    pillar_id="performance-efficiency",
    title="Monitor training and inference performance",
    principle="Monitor performance",
)

_JOB_ROWS = [{"total_runs": 30, "avg_duration_s": 240.0, "max_duration_s": 1800.0}]
_SERVING_ROWS = [
    {
        "total_requests": 5000,
        "avg_latency_ms": 55.0,
        "max_latency_ms": 980.0,
        "active_endpoints": 2,
    }
]


def _ctx(*, job_rows=None, serving_rows=None, llm_response: str | None = "") -> AgentContext:
    responses = {
        "avg_duration_s": job_rows if job_rows is not None else _JOB_ROWS,
        "total_requests": serving_rows if serving_rows is not None else _SERVING_ROWS,
    }
    return AgentContext(
        assessment_id="test-ml-pe05",
        layer="ml",
        sql=FakeSqlClient(responses),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_training_duration_summary():
    ev = MlPerformanceMonitoringCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "30" in ev[0].summary
    assert "avg=240.0s" in ev[0].summary


def test_collect_inference_latency_summary():
    ev = MlPerformanceMonitoringCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "5,000" in ev[1].summary or "5000" in ev[1].summary
    assert "2" in ev[1].summary  # 2 active endpoints


def test_collect_no_job_runs():
    ev = MlPerformanceMonitoringCheck().collect(_ctx(job_rows=[]))
    assert "No completed job runs" in ev[0].summary


def test_collect_no_serving_traffic():
    ev = MlPerformanceMonitoringCheck().collect(_ctx(serving_rows=[]))
    assert "No serving endpoint traffic" in ev[1].summary


def test_collect_attaches_limitation_note():
    ev = MlPerformanceMonitoringCheck().collect(_ctx())
    assert ev[2].kind == "note"
    summary_lower = ev[2].summary.lower()
    assert "active monitoring" in summary_lower or "actively monitored" in summary_lower


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium", "score": null,'
        ' "rationale": "Telemetry exists but no dashboards confirmed"}'
    )
    f = MlPerformanceMonitoringCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.sources


def test_no_llm_degrades_to_unassessed():
    f = MlPerformanceMonitoringCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
