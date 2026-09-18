from __future__ import annotations

from waf_agents.analytics.checks.co_warehouse_autostop import WarehouseAutoStopCheck
from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-CO-02",
    pillar_id="cost-optimization",
    title="Enable warehouse auto-stop when idle",
    principle="Avoid idle compute spend",
)


def _ctx(total: int, auto_stop: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(
            {"auto_stop_minutes": [{"total": total, "auto_stop": auto_stop}]}
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = WarehouseAutoStopCheck().run(_Q, _ctx(10, 10))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 1.0
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = WarehouseAutoStopCheck().run(_Q, _ctx(10, 6))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.6


def test_not_met():
    f = WarehouseAutoStopCheck().run(_Q, _ctx(10, 2))
    assert f.verdict is Verdict.NOT_MET
    assert f.score == 0.2


def test_no_warehouses_is_unknown_low():
    f = WarehouseAutoStopCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
