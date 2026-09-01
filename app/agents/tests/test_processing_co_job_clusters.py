from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.co_job_clusters import ProcessingJobClustersCheck

_Q = Question(
    id="PRO-CO-01",
    pillar_id="cost-optimization",
    title="Use job clusters for transformation workloads",
    principle="Optimize compute cost for scheduled workloads",
)


def _ctx(total_dbus: float, all_purpose_dbus: float) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient({
            "system.billing.usage": [
                {"total_dbus": total_dbus, "all_purpose_dbus": all_purpose_dbus}
            ]
        }),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = ProcessingJobClustersCheck().run(_Q, _ctx(100.0, 5.0))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.95
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    # 70% job/serverless (30 all-purpose) -> 0.70 between 0.60 and 0.90 -> PARTIAL
    f = ProcessingJobClustersCheck().run(_Q, _ctx(100.0, 30.0))
    assert f.verdict is Verdict.PARTIAL


def test_not_met():
    # 20% job/serverless (80 all-purpose) -> 0.20 < 0.60 -> NOT_MET
    f = ProcessingJobClustersCheck().run(_Q, _ctx(100.0, 80.0))
    assert f.verdict is Verdict.NOT_MET


def test_empty_is_unknown_low():
    f = ProcessingJobClustersCheck().run(_Q, _ctx(0.0, 0.0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
