from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.co_autoscaling_termination import (
    ProcessingAutoscalingTerminationCheck,
)

_Q = Question(
    id="PRO-CO-03",
    pillar_id="cost-optimization",
    title="Use autoscaling and auto-termination for processing",
    principle="Optimize compute cost and resource utilization",
)


def _ctx(as_total: int, as_count: int, at_total: int, at_count: int) -> AgentContext:
    # Needles are distinct, non-overlapping substrings of the two SQL strings:
    #   "max_autoscale_workers" -> _AUTOSCALING_SQL
    #   "auto_termination_minutes" -> _AUTOTERMINATION_SQL
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient({
            "max_autoscale_workers": [{"total": as_total, "autoscaling": as_count}],
            "auto_termination_minutes": [{"total": at_total, "auto_term": at_count}],
        }),
        catalogs=["main"],
    )


def test_met_when_both_above_threshold():
    # autoscaling 9/10 = 90%, auto-term 5/5 = 100%; min = 90% >= 80% -> MET
    f = ProcessingAutoscalingTerminationCheck().run(_Q, _ctx(10, 9, 5, 5))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.9


def test_partial_when_autoscaling_below_met():
    # autoscaling 5/10 = 50%, auto-term 5/5 = 100%; min = 50% -> PARTIAL
    f = ProcessingAutoscalingTerminationCheck().run(_Q, _ctx(10, 5, 5, 5))
    assert f.verdict is Verdict.PARTIAL


def test_not_met_when_both_low():
    # autoscaling 1/10 = 10%, auto-term 1/5 = 20%; min = 10% < 40% -> NOT_MET
    f = ProcessingAutoscalingTerminationCheck().run(_Q, _ctx(10, 1, 5, 1))
    assert f.verdict is Verdict.NOT_MET


def test_empty_is_unknown_low():
    f = ProcessingAutoscalingTerminationCheck().run(_Q, _ctx(0, 0, 0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
