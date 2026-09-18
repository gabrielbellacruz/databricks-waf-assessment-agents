from __future__ import annotations

from waf_agents.analytics.checks.co_warehouse_sizing import WarehouseSizingCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-CO-01",
    pillar_id="cost-optimization",
    title="Use SQL warehouses sized to analytics workloads",
    principle="Right-size compute to match demand and control cost",
)

# Needles are distinct substrings of the two SQL strings:
#   "warehouse_size" -> _WAREHOUSE_SQL (SELECT warehouse_size, warehouse_type, ...)
#   "statement_type" -> _QUERY_LOAD_SQL (AND statement_type = 'SELECT')
_WH_ROWS = [
    {
        "warehouse_size": "LARGE",
        "warehouse_type": "PRO",
        "min_clusters": 1,
        "max_clusters": 3,
        "cnt": 2,
    },
    {
        "warehouse_size": "SMALL",
        "warehouse_type": "CLASSIC",
        "min_clusters": 1,
        "max_clusters": 1,
        "cnt": 1,
    },
]

_QLOAD_ROWS = [
    {
        "query_count": 450,
        "avg_duration_ms": 3200.0,
        "max_duration_ms": 45000,
        "slow_query_count": 12,
    }
]


def _ctx(
    *,
    wh_rows: list[dict] | None = None,
    qload_rows: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    responses: dict[str, list[dict]] = {}
    if wh_rows is not None:
        responses["warehouse_size"] = wh_rows
    if qload_rows is not None:
        responses["statement_type"] = qload_rows
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(responses),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_warehouse_summary():
    ev = WarehouseSizingCheck().collect(_ctx(wh_rows=_WH_ROWS))
    assert ev[0].kind == "sql"
    # 2+1 = 3 total warehouses across 2 configurations
    assert "3 active warehouses" in ev[0].summary
    assert "2 size/type configurations" in ev[0].summary


def test_collect_no_warehouses_summary():
    ev = WarehouseSizingCheck().collect(_ctx(wh_rows=[]))
    assert "No active warehouses" in ev[0].summary


def test_collect_query_load_evidence():
    ev = WarehouseSizingCheck().collect(_ctx(wh_rows=_WH_ROWS, qload_rows=_QLOAD_ROWS))
    assert ev[1].kind == "sql"
    assert "450 SELECT queries" in ev[1].summary
    assert "12 slow" in ev[1].summary


def test_collect_returns_note():
    ev = WarehouseSizingCheck().collect(_ctx())
    note = next(e for e in ev if e.kind == "note")
    assert "Manual review" in note.summary


def test_judge_maps_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium", "score": null,'
        ' "rationale": "Warehouses appear appropriately sized for workloads"}'
    )
    f = WarehouseSizingCheck().run(_Q, _ctx(wh_rows=_WH_ROWS, llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.sources


def test_judge_caps_confidence_from_high():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "Some warehouses may be oversized"}'
    )
    f = WarehouseSizingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_is_unassessed_with_sources():
    f = WarehouseSizingCheck().run(_Q, _ctx(wh_rows=_WH_ROWS, llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
