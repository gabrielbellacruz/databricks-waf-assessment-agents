from __future__ import annotations

from waf_agents.analytics.checks.oe_warehouse_monitoring import WarehouseMonitoringCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-OE-02",
    pillar_id="operational-excellence",
    title="Monitor SQL warehouse health and query failures",
    principle="Set up Monitoring, Alerting and Logging",
)

# Needles are distinct substrings of the two SQL strings:
#   "query.history"    -> _QUERY_HISTORY_SQL (FROM system.query.history)
#   "warehouse_events" -> _WAREHOUSE_EVENTS_SQL (FROM system.compute.warehouse_events)


def _ctx(
    *,
    qh_rows: list[dict] | None = None,
    we_rows: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    responses: dict[str, list[dict]] = {}
    if qh_rows is not None:
        responses["query.history"] = qh_rows
    if we_rows is not None:
        responses["warehouse_events"] = we_rows
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(responses),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_shows_query_failure_rate():
    ev = WarehouseMonitoringCheck().collect(
        _ctx(qh_rows=[{"total_queries": 200, "failed_queries": 10}])
    )
    assert ev[0].kind == "sql"
    assert "10 of 200" in ev[0].summary
    assert "5.0%" in ev[0].summary


def test_collect_zero_queries_shows_no_queries_message():
    ev = WarehouseMonitoringCheck().collect(_ctx(qh_rows=[]))
    assert "No queries found" in ev[0].summary


def test_collect_shows_warehouse_event_counts():
    ev = WarehouseMonitoringCheck().collect(
        _ctx(we_rows=[{"event_count": 50, "warehouse_count": 3}])
    )
    assert "50 warehouse events" in ev[1].summary
    assert "3 warehouse(s)" in ev[1].summary


def test_collect_includes_note_evidence():
    ev = WarehouseMonitoringCheck().collect(_ctx())
    kinds = [e.kind for e in ev]
    assert "note" in kinds


def test_collect_evidence_has_rows():
    ev = WarehouseMonitoringCheck().collect(
        _ctx(qh_rows=[{"total_queries": 100, "failed_queries": 5}])
    )
    assert any(r.get("total_queries") == 100 for r in ev[0].rows)
    assert any(r.get("failed_queries") == 5 for r in ev[0].rows)


def test_judge_maps_llm_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Low failure rate suggests healthy monitoring"}'
    )
    f = WarehouseMonitoringCheck().run(
        _Q,
        _ctx(
            qh_rows=[{"total_queries": 100, "failed_queries": 2}],
            llm_response=resp,
        ),
    )
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Moderate failures"}'
    )
    f = WarehouseMonitoringCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_returns_unassessed_with_sources():
    f = WarehouseMonitoringCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
