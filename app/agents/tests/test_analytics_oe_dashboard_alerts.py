from __future__ import annotations

from waf_agents.analytics.checks.oe_dashboard_alerts import DashboardAlertsCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-OE-04",
    pillar_id="operational-excellence",
    title="Alert on stale or broken dashboards",
    principle="Set up Monitoring, Alerting and Logging",
)

# Needle: "query.history" -> _SQL (FROM system.query.history)


def _ctx(
    *,
    qh_rows: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient({"query.history": qh_rows or []}),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_shows_failure_and_canceled_counts():
    rows = [{"total_queries": 500, "failed_queries": 25, "canceled_queries": 5}]
    ev = DashboardAlertsCheck().collect(_ctx(qh_rows=rows))
    assert ev[0].kind == "sql"
    assert "25 of 500" in ev[0].summary
    assert "5.0%" in ev[0].summary


def test_collect_zero_queries_shows_no_queries_message():
    ev = DashboardAlertsCheck().collect(_ctx(qh_rows=[]))
    assert "No queries found" in ev[0].summary


def test_collect_includes_alert_note():
    ev = DashboardAlertsCheck().collect(_ctx())
    kinds = [e.kind for e in ev]
    assert "note" in kinds


def test_collect_evidence_rows_contain_all_fields():
    rows = [{"total_queries": 200, "failed_queries": 10, "canceled_queries": 3}]
    ev = DashboardAlertsCheck().collect(_ctx(qh_rows=rows))
    assert any(r.get("total_queries") == 200 for r in ev[0].rows)
    assert any(r.get("canceled_queries") == 3 for r in ev[0].rows)


def test_judge_not_met_high_failure_rate():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "High failure rate with no evidence of alerting"}'
    )
    rows = [{"total_queries": 100, "failed_queries": 30, "canceled_queries": 5}]
    f = DashboardAlertsCheck().run(_Q, _ctx(qh_rows=rows, llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "No failures"}'
    )
    f = DashboardAlertsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_returns_unassessed_with_sources():
    rows = [{"total_queries": 100, "failed_queries": 30, "canceled_queries": 5}]
    f = DashboardAlertsCheck().run(_Q, _ctx(qh_rows=rows, llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
