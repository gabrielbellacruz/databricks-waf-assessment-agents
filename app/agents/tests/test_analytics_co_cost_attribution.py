from __future__ import annotations

from waf_agents.analytics.checks.co_cost_attribution import AnalyticsCostAttributionCheck
from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-CO-04",
    pillar_id="cost-optimization",
    title="Attribute analytics/warehouse cost to teams",
    principle="Maintain visibility and accountability for cost",
)


def _ctx(total: int, tagged: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(
            {"custom_tags": [{"total": total, "tagged": tagged}]}
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = AnalyticsCostAttributionCheck().run(_Q, _ctx(100, 90))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.9
    assert f.sources and f.sources[0].kind == "sql"


def test_partial_and_not_met():
    assert AnalyticsCostAttributionCheck().run(_Q, _ctx(100, 50)).verdict is Verdict.PARTIAL
    assert AnalyticsCostAttributionCheck().run(_Q, _ctx(100, 10)).verdict is Verdict.NOT_MET


def test_no_usage_is_unknown_low():
    f = AnalyticsCostAttributionCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
