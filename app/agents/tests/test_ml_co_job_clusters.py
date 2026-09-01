from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.co_job_clusters import MlJobClustersCheck

_Q = Question(
    id="ML-CO-02",
    pillar_id="cost-optimization",
    title="Use job clusters for training runs",
    principle="Optimise compute spend",
)

# Unique needle in the SQL: "all_purpose_gpu_dbus" appears in the SQL alias.
# Additionally the SQL filters "ILIKE '%GPU%'" — use "all_purpose_gpu_dbus" as needle.
_SQL_NEEDLE = "all_purpose_gpu_dbus"


def _ctx(total_gpu: float, all_purpose_gpu: float) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(
            {
                _SQL_NEEDLE: [
                    {"total_gpu_dbus": total_gpu, "all_purpose_gpu_dbus": all_purpose_gpu}
                ]
            }
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    # 90% on job clusters -> MET
    f = MlJobClustersCheck().run(_Q, _ctx(100.0, 10.0))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.9


def test_partial():
    # 60% on job clusters -> PARTIAL
    f = MlJobClustersCheck().run(_Q, _ctx(100.0, 40.0))
    assert f.verdict is Verdict.PARTIAL


def test_not_met():
    # 20% on job clusters -> NOT_MET
    f = MlJobClustersCheck().run(_Q, _ctx(100.0, 80.0))
    assert f.verdict is Verdict.NOT_MET


def test_no_gpu_usage_is_unknown_low():
    f = MlJobClustersCheck().run(_Q, _ctx(0.0, 0.0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_sources_attached():
    f = MlJobClustersCheck().run(_Q, _ctx(100.0, 10.0))
    assert f.sources
    assert f.sources[0].kind == "sql"


def test_score_is_rounded_ratio():
    f = MlJobClustersCheck().run(_Q, _ctx(300.0, 45.0))
    # compliant = 255, ratio = 255/300 = 0.85
    assert f.score == round(255 / 300, 4)
