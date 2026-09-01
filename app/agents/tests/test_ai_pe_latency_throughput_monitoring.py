from __future__ import annotations

from waf_agents.ai.checks.pe_latency_throughput_monitoring import LatencyThroughputMonitoringCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-PE-05",
    pillar_id="pe",
    title="Monitor endpoint latency and throughput",
    principle="Maintain observability into AI serving performance with active alerting",
)

# Needle: "monitored_endpoints" — unique alias in the monitoring summary SQL
_FAKE = {
    "monitored_endpoints": [
        {
            "monitored_endpoints": 4,
            "total_monitored_requests": 50000,
            "avg_latency_ms": 320.5,
            "max_latency_ms": 8500,
            "earliest_date": "2024-01-01",
            "latest_date": "2024-01-30",
        }
    ]
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def _ctx_empty(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_endpoint_count():
    ev = LatencyThroughputMonitoringCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "4 endpoint(s)" in ev[0].summary


def test_collect_request_count():
    ev = LatencyThroughputMonitoringCheck().collect(_ctx())
    assert "50000 requests" in ev[0].summary


def test_collect_latency_values():
    ev = LatencyThroughputMonitoringCheck().collect(_ctx())
    assert "avg=320.5ms" in ev[0].summary
    assert "max=8500ms" in ev[0].summary


def test_collect_confirms_data_available():
    ev = LatencyThroughputMonitoringCheck().collect(_ctx())
    assert "monitoring data exists" in ev[0].summary


def test_collect_has_rows():
    ev = LatencyThroughputMonitoringCheck().collect(_ctx())
    assert ev[0].rows[0]["monitored_endpoints"] == 4
    assert ev[0].rows[0]["total_monitored_requests"] == 50000


def test_collect_note_evidence():
    ev = LatencyThroughputMonitoringCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "monitoring" in ev[1].summary.lower()


def test_collect_empty_no_crash():
    ev = LatencyThroughputMonitoringCheck().collect(_ctx_empty())
    assert "No serving endpoint telemetry" in ev[0].summary


def test_judge_maps_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium", "score": null,'
        ' "rationale": "Telemetry exists but active alerting unconfirmed"}'
    )
    f = LatencyThroughputMonitoringCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.sources


def test_judge_caps_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Full observability"}'
    )
    f = LatencyThroughputMonitoringCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = LatencyThroughputMonitoringCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
