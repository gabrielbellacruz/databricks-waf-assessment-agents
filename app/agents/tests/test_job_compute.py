from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.job_compute import JobComputeCheck

_Q = Question(
    id="ING-CO-01",
    pillar_id="cost-optimization",
    title="Use job clusters for scheduled ingestion",
    principle="Optimize cost",
)


def _ctx(total_dbus: float, all_purpose_dbus: float) -> AgentContext:
    rows = [{"total_dbus": total_dbus, "all_purpose_dbus": all_purpose_dbus}]
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient({"system.billing.usage": rows}),
        catalogs=["main"],
    )


def test_met_high_confidence():
    # 95 of 100 DBUs on job/serverless -> ratio 0.95 >= 0.90 -> MET
    f = JobComputeCheck().run(_Q, _ctx(100.0, 5.0))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.95
    assert f.sources and f.sources[0].kind == "sql"


def test_partial_and_not_met():
    # 70 of 100 DBUs job/serverless -> ratio 0.70 -> PARTIAL
    assert JobComputeCheck().run(_Q, _ctx(100.0, 30.0)).verdict is Verdict.PARTIAL
    # 50 of 100 DBUs job/serverless -> ratio 0.50 -> NOT_MET
    assert JobComputeCheck().run(_Q, _ctx(100.0, 50.0)).verdict is Verdict.NOT_MET


def test_no_usage_is_unknown_low():
    f = JobComputeCheck().run(_Q, _ctx(0.0, 0.0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
