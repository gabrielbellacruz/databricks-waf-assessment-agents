from __future__ import annotations

from waf_agents.analytics.checks.r_autoscaling_warehouses import WarehouseAutoscalingCheck
from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-R-01",
    pillar_id="reliability",
    title="Use autoscaling SQL warehouses",
    principle="Absorb concurrent analytics load without manual intervention",
)


def _ctx(total: int, autoscaling: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(
            {"max_num_clusters": [{"total": total, "autoscaling": autoscaling}]}
        ),
    )


def test_met_high_confidence():
    f = WarehouseAutoscalingCheck().run(_Q, _ctx(10, 8))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.8
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = WarehouseAutoscalingCheck().run(_Q, _ctx(10, 5))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_not_met():
    f = WarehouseAutoscalingCheck().run(_Q, _ctx(10, 2))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.HIGH


def test_empty_is_unknown_low():
    f = WarehouseAutoscalingCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_score_rounded():
    f = WarehouseAutoscalingCheck().run(_Q, _ctx(3, 2))
    assert f.score == round(2 / 3, 4)


def test_evidence_rows_attached():
    f = WarehouseAutoscalingCheck().run(_Q, _ctx(10, 7))
    assert f.sources[0].rows[0]["total"] == 10
    assert f.sources[0].rows[0]["autoscaling"] == 7
