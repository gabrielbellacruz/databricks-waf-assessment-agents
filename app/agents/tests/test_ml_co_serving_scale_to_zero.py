from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.co_serving_scale_to_zero import ServingScaleToZeroCheck

_Q = Question(
    id="ML-CO-04",
    pillar_id="cost-optimization",
    title="Scale serving endpoints to zero when idle",
    principle="Optimise serving cost",
)

# Unique needle: "idle_cost_hours" is only in this check's SQL.
_SQL_NEEDLE = "idle_cost_hours"


def _ctx(total: int, idle_cost: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(
            {_SQL_NEEDLE: [{"total_endpoint_hours": total, "idle_cost_hours": idle_cost}]}
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    # 5% idle cost -> compliance 0.95 -> MET
    f = ServingScaleToZeroCheck().run(_Q, _ctx(100, 5))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == round(95 / 100, 4)


def test_partial():
    # 50% idle cost -> compliance 0.50 -> PARTIAL (between 0.40 and 0.80)
    f = ServingScaleToZeroCheck().run(_Q, _ctx(100, 50))
    assert f.verdict is Verdict.PARTIAL


def test_not_met():
    # 80% idle cost -> compliance 0.20 -> NOT_MET (below 0.40)
    f = ServingScaleToZeroCheck().run(_Q, _ctx(100, 80))
    assert f.verdict is Verdict.NOT_MET


def test_no_usage_is_unknown_low():
    f = ServingScaleToZeroCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_sources_attached():
    f = ServingScaleToZeroCheck().run(_Q, _ctx(100, 5))
    assert f.sources
    assert f.sources[0].kind == "sql"


def test_no_idle_cost_is_met():
    # All hours have traffic -> no idle cost -> MET
    f = ServingScaleToZeroCheck().run(_Q, _ctx(100, 0))
    assert f.verdict is Verdict.MET
    assert f.score == 1.0


def test_rationale_mentions_percentage():
    f = ServingScaleToZeroCheck().run(_Q, _ctx(100, 80))
    assert "80%" in f.rationale
