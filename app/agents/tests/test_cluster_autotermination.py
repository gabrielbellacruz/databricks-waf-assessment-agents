from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.cluster_autotermination import ClusterAutoterminationCheck

_Q = Question(
    id="ING-CO-03",
    pillar_id="cost-optimization",
    title="Auto-terminate ingestion compute when idle",
    principle="Monitor and control cost",
)


def _ctx(total: int, auto_term: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient(
            {"system.compute.clusters": [{"total": total, "auto_term": auto_term}]}
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = ClusterAutoterminationCheck().run(_Q, _ctx(100, 90))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.9
    assert f.sources and f.sources[0].kind == "sql"


def test_partial_and_not_met():
    assert ClusterAutoterminationCheck().run(_Q, _ctx(100, 50)).verdict is Verdict.PARTIAL
    assert ClusterAutoterminationCheck().run(_Q, _ctx(100, 10)).verdict is Verdict.NOT_MET


def test_no_clusters_is_unknown_low():
    f = ClusterAutoterminationCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
