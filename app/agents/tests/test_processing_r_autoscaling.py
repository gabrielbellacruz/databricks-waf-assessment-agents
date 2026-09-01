from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.r_autoscaling import ProcessingAutoscalingCheck

_Q = Question(
    id="PRO-R-05",
    pillar_id="reliability",
    title="Enable autoscaling for transformation workloads",
    principle="Design for reliability",
)


def _ctx(total: int, autoscaling: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient(
            {"system.compute.clusters": [{"total": total, "autoscaling": autoscaling}]}
        ),
        catalogs=["main"],
    )


def test_met_medium_confidence():
    f = ProcessingAutoscalingCheck().run(_Q, _ctx(10, 8))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.8
    assert f.sources and f.sources[0].kind == "sql"


def test_partial_medium_confidence():
    f = ProcessingAutoscalingCheck().run(_Q, _ctx(10, 5))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_not_met_medium_confidence():
    f = ProcessingAutoscalingCheck().run(_Q, _ctx(10, 1))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_empty_clusters_unknown_low():
    f = ProcessingAutoscalingCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_score_is_ratio():
    f = ProcessingAutoscalingCheck().run(_Q, _ctx(10, 7))
    assert f.verdict is Verdict.MET
    assert f.score == 0.7


def test_collect_evidence_has_rows():
    ev = ProcessingAutoscalingCheck().collect(_ctx(5, 4))
    assert ev[0].rows[0]["total"] == 5
    assert ev[0].rows[0]["autoscaling"] == 4
