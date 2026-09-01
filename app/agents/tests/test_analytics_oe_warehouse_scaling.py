from __future__ import annotations

from waf_agents.analytics.checks.oe_warehouse_scaling import WarehouseScalingCheck
from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-OE-05",
    pillar_id="operational-excellence",
    title="Manage warehouse concurrency and scaling",
    principle="Manage capacity and quotas",
)

# Needle: "system.compute.warehouses" -> _SQL (FROM system.compute.warehouses)


def _ctx(total: int, scaling: int, autostop: int = 0) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(
            {
                "system.compute.warehouses": [
                    {
                        "total_warehouses": total,
                        "scaling_warehouses": scaling,
                        "autostop_warehouses": autostop,
                    }
                ]
            }
        ),
    )


def test_met_all_warehouses_have_scaling():
    f = WarehouseScalingCheck().run(_Q, _ctx(5, 5))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 1.0


def test_met_at_threshold():
    # 8/10 = 0.80 -> exactly at met threshold
    f = WarehouseScalingCheck().run(_Q, _ctx(10, 8))
    assert f.verdict is Verdict.MET
    assert f.score == 0.8


def test_partial_above_partial_threshold():
    # 5/10 = 0.50 -> partial
    f = WarehouseScalingCheck().run(_Q, _ctx(10, 5))
    assert f.verdict is Verdict.PARTIAL
    assert f.score == 0.5


def test_partial_at_partial_threshold():
    # 4/10 = 0.40 -> exactly at partial threshold
    f = WarehouseScalingCheck().run(_Q, _ctx(10, 4))
    assert f.verdict is Verdict.PARTIAL
    assert f.score == 0.4


def test_not_met_below_partial_threshold():
    # 2/10 = 0.20 -> not_met
    f = WarehouseScalingCheck().run(_Q, _ctx(10, 2))
    assert f.verdict is Verdict.NOT_MET
    assert f.score == 0.2


def test_not_met_no_scaling_warehouses():
    f = WarehouseScalingCheck().run(_Q, _ctx(5, 0))
    assert f.verdict is Verdict.NOT_MET
    assert f.score == 0.0


def test_empty_is_unknown_low_confidence():
    f = WarehouseScalingCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_score_is_rounded_to_four_decimal_places():
    # 7/9 = 0.7778
    f = WarehouseScalingCheck().run(_Q, _ctx(9, 7))
    assert f.score is not None
    assert len(str(f.score).split(".")[-1]) <= 4


def test_sources_attached():
    f = WarehouseScalingCheck().run(_Q, _ctx(3, 2))
    assert f.sources and f.sources[0].kind == "sql"
