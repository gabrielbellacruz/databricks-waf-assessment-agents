from __future__ import annotations

from waf_agents.analytics.checks.iu_bi_connectivity import BiConnectivityCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-IU-01",
    pillar_id="interoperability-usability",
    title="Connect BI tools via standard interfaces",
    principle="BI tools should use standard JDBC/ODBC/REST interfaces via SQL warehouses",
)

# Needles: 'total_warehouses' matches _WAREHOUSE_SQL,
#          'distinct_users' matches _QUERY_ACTIVITY_SQL.
_FAKE_RESPONSES = {
    "total_warehouses": [{"total_warehouses": 3, "running_warehouses": 1}],
    "distinct_users": [{"recent_queries": 1500, "distinct_users": 25}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_warehouse_evidence():
    ev = BiConnectivityCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "3" in ev[0].summary
    assert "warehouse" in ev[0].summary.lower()


def test_collect_activity_evidence():
    ev = BiConnectivityCheck().collect(_ctx())
    assert len(ev) == 2
    assert "1500" in ev[1].summary
    assert "25" in ev[1].summary


def test_judge_met():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "SQL warehouses active with significant query volume"}'
    )
    f = BiConnectivityCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_no_warehouses():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "No SQL warehouses found"}'
    )
    f = BiConnectivityCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = BiConnectivityCheck().run(_Q, _ctx(llm_response=None))
    assert f.auto_assessable is False
    assert f.sources
