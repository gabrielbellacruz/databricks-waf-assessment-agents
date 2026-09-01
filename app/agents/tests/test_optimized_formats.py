from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.optimized_formats import OptimizedFormatsCheck

_Q = Question(
    id="STO-CO-01",
    pillar_id="cost-optimization",
    title="Store data in performance-optimized formats",
    principle="Use columnar formats to minimize query cost and improve performance",
)


def _ctx(total: int, optimized_count: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(
            {"information_schema.tables": [{"total": total, "optimized_count": optimized_count}]}
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = OptimizedFormatsCheck().run(_Q, _ctx(100, 85))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.85
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = OptimizedFormatsCheck().run(_Q, _ctx(100, 60))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_not_met():
    f = OptimizedFormatsCheck().run(_Q, _ctx(100, 30))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.HIGH


def test_empty_is_unknown_low():
    f = OptimizedFormatsCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
    assert f.auto_assessable is True
