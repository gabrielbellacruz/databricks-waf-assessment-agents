from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.co_cost_tagging import MlCostTaggingCheck

_Q = Question(
    id="ML-CO-05",
    pillar_id="cost-optimization",
    title="Attribute ML training and serving cost",
    principle="Attribute and control cost",
)

# Unique needle: "MACHINE_LEARN" appears only in this check's SQL filter.
_SQL_NEEDLE = "MACHINE_LEARN"


def _ctx(total: int, tagged: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(
            {_SQL_NEEDLE: [{"total": total, "tagged": tagged}]}
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    # 90% tagged -> MET
    f = MlCostTaggingCheck().run(_Q, _ctx(100, 90))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.9


def test_partial():
    # 60% tagged -> PARTIAL
    f = MlCostTaggingCheck().run(_Q, _ctx(100, 60))
    assert f.verdict is Verdict.PARTIAL


def test_not_met():
    # 20% tagged -> NOT_MET
    f = MlCostTaggingCheck().run(_Q, _ctx(100, 20))
    assert f.verdict is Verdict.NOT_MET


def test_no_ml_usage_is_unknown_low():
    f = MlCostTaggingCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_sources_attached():
    f = MlCostTaggingCheck().run(_Q, _ctx(100, 90))
    assert f.sources
    assert f.sources[0].kind == "sql"


def test_score_is_rounded_ratio():
    f = MlCostTaggingCheck().run(_Q, _ctx(300, 240))
    # 240/300 = 0.8
    assert f.score == round(240 / 300, 4)


def test_rationale_mentions_threshold():
    f = MlCostTaggingCheck().run(_Q, _ctx(100, 50))
    assert "80%" in f.rationale
