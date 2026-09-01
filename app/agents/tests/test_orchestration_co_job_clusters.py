from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.co_job_clusters import OrcJobClustersCheck

_Q = Question(
    id="ORC-CO-01",
    pillar_id="cost-optimization",
    title="Run workflows on job clusters",
    principle="Optimize cost",
)

# FakeSqlClient matches SQL containing "all_purpose_dbus" (unique alias in this check's SQL).
def _ctx(total_dbus: float, all_purpose_dbus: float) -> AgentContext:
    rows = [{"total_dbus": total_dbus, "all_purpose_dbus": all_purpose_dbus}]
    return AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient({"all_purpose_dbus": rows}),
        catalogs=["main"],
    )


def test_orchestration_co01_met_high_confidence():
    # 95 of 100 workflow DBUs on job/serverless -> ratio 0.95 >= 0.90 -> MET
    f = OrcJobClustersCheck().run(_Q, _ctx(100.0, 5.0))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.95
    assert f.sources and f.sources[0].kind == "sql"


def test_orchestration_co01_partial():
    # 70 of 100 DBUs job/serverless -> ratio 0.70 -> PARTIAL
    f = OrcJobClustersCheck().run(_Q, _ctx(100.0, 30.0))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_orchestration_co01_not_met():
    # 50 of 100 DBUs job/serverless -> ratio 0.50 < 0.60 -> NOT_MET
    f = OrcJobClustersCheck().run(_Q, _ctx(100.0, 50.0))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.HIGH


def test_orchestration_co01_no_usage_unknown_low():
    f = OrcJobClustersCheck().run(_Q, _ctx(0.0, 0.0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
    assert f.sources


def test_orchestration_co01_evidence_has_rows():
    check = OrcJobClustersCheck()
    ev = check.collect(
        AgentContext(
            assessment_id="a1",
            layer="orchestration",
            sql=FakeSqlClient(
                {"all_purpose_dbus": [{"total_dbus": 200.0, "all_purpose_dbus": 20.0}]}
            ),
            catalogs=["main"],
        )
    )
    assert ev[0].rows[0]["total_dbus"] == 200.0
    assert ev[0].rows[0]["all_purpose_dbus"] == 20.0
