from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.cost_tagging import CostTaggingCheck

_Q = Question(
    id="ING-CO-04",
    pillar_id="cost-optimization",
    title="Tag and attribute ingestion costs",
    principle="Monitor and control cost",
)


def _ctx(total: int, tagged: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient({"system.billing.usage": [{"total": total, "tagged": tagged}]}),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = CostTaggingCheck().run(_Q, _ctx(100, 90))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.9
    assert f.sources and f.sources[0].kind == "sql"


def test_partial_and_not_met():
    assert CostTaggingCheck().run(_Q, _ctx(100, 50)).verdict is Verdict.PARTIAL
    assert CostTaggingCheck().run(_Q, _ctx(100, 10)).verdict is Verdict.NOT_MET


def test_no_usage_is_unknown_low():
    f = CostTaggingCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
