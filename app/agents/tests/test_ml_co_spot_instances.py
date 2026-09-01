from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.co_spot_instances import SpotInstancesCheck

_Q = Question(
    id="ML-CO-03",
    pillar_id="cost-optimization",
    title="Use spot/preemptible instances for tolerant training",
    principle="Optimise compute spend",
)

# Unique needle: "spot_clusters" appears in the SQL alias and is unique to this check.
_SQL_NEEDLE = "spot_clusters"


def _ctx(total: int, spot: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(
            {_SQL_NEEDLE: [{"total_job_clusters": total, "spot_clusters": spot}]}
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    # 70% spot -> above 0.60 threshold -> MET
    f = SpotInstancesCheck().run(_Q, _ctx(10, 7))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == round(7 / 10, 4)


def test_partial():
    # 40% spot -> between 0.30 and 0.60 -> PARTIAL
    f = SpotInstancesCheck().run(_Q, _ctx(10, 4))
    assert f.verdict is Verdict.PARTIAL


def test_not_met():
    # 10% spot -> below 0.30 -> NOT_MET
    f = SpotInstancesCheck().run(_Q, _ctx(10, 1))
    assert f.verdict is Verdict.NOT_MET


def test_no_job_clusters_is_unknown_low():
    f = SpotInstancesCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_sources_attached():
    f = SpotInstancesCheck().run(_Q, _ctx(10, 7))
    assert f.sources
    assert f.sources[0].kind == "sql"


def test_all_spot_is_met():
    f = SpotInstancesCheck().run(_Q, _ctx(5, 5))
    assert f.verdict is Verdict.MET
    assert f.score == 1.0


def test_rationale_mentions_threshold():
    f = SpotInstancesCheck().run(_Q, _ctx(10, 3))
    assert "60%" in f.rationale
