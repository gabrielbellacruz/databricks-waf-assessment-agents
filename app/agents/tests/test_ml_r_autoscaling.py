from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.r_autoscaling import MlAutoscalingCheck

_Q = Question(
    id="ML-R-05",
    pillar_id="reliability",
    title="Autoscale training and serving to demand",
    principle="Design for autoscaling",
)


def _ctx(total: int, autoscaling: int) -> AgentContext:
    return AgentContext(
        assessment_id="test-ml-r05",
        layer="ml",
        sql=FakeSqlClient(
            {"delete_time IS NULL": [{"total": total, "autoscaling_enabled": autoscaling}]}
        ),
    )


def test_met_high_autoscaling_ratio():
    f = MlAutoscalingCheck().run(_Q, _ctx(10, 8))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.8


def test_partial_moderate_autoscaling():
    f = MlAutoscalingCheck().run(_Q, _ctx(10, 5))
    assert f.verdict is Verdict.PARTIAL
    assert f.score == 0.5


def test_not_met_low_autoscaling():
    f = MlAutoscalingCheck().run(_Q, _ctx(10, 2))
    assert f.verdict is Verdict.NOT_MET
    assert f.score == 0.2


def test_empty_clusters_is_unknown_low():
    f = MlAutoscalingCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_collect_attaches_note_evidence():
    ev = MlAutoscalingCheck().collect(
        AgentContext(
            assessment_id="x",
            layer="ml",
            sql=FakeSqlClient({"delete_time IS NULL": [{"total": 5, "autoscaling_enabled": 3}]}),
        )
    )
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "serving-endpoint" in ev[1].summary


def test_score_is_ratio():
    f = MlAutoscalingCheck().run(_Q, _ctx(100, 75))
    assert f.score == 0.75
