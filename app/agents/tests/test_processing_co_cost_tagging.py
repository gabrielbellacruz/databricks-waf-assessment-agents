from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.co_cost_tagging import ProcessingCostTaggingCheck

_Q = Question(
    id="PRO-CO-05",
    pillar_id="cost-optimization",
    title="Attribute processing cost with tags and policies",
    principle="Monitor and control cost",
)


def _ctx(total: int, tagged: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient({"system.billing.usage": [{"total": total, "tagged": tagged}]}),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = ProcessingCostTaggingCheck().run(_Q, _ctx(100, 90))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.9
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = ProcessingCostTaggingCheck().run(_Q, _ctx(100, 50))
    assert f.verdict is Verdict.PARTIAL


def test_not_met():
    f = ProcessingCostTaggingCheck().run(_Q, _ctx(100, 10))
    assert f.verdict is Verdict.NOT_MET


def test_empty_is_unknown_low():
    f = ProcessingCostTaggingCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
