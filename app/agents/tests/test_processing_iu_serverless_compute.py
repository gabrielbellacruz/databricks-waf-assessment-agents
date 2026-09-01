from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.iu_serverless_compute import (
    ProcessingServerlessComputeCheck,
)

_Q = Question(
    id="PRO-IU-03",
    pillar_id="interoperability-usability",
    title="Use serverless compute for transformations",
    principle="Eliminate cluster management overhead for transformation workloads",
)

# SQL needle: "SERVERLESS"
def _ctx(total: float, serverless: float) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient(
            {"SERVERLESS": [{"total_dbus": total, "serverless_dbus": serverless}]}
        ),
        catalogs=["main"],
    )


def test_met_high_serverless():
    # 600 of 1000 → 60% → MET (threshold 50%)
    f = ProcessingServerlessComputeCheck().run(_Q, _ctx(1000.0, 600.0))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.60
    assert f.sources and f.sources[0].kind == "sql"


def test_partial_serverless():
    # 200 of 1000 → 20% → PARTIAL (15–50%)
    f = ProcessingServerlessComputeCheck().run(_Q, _ctx(1000.0, 200.0))
    assert f.verdict is Verdict.PARTIAL


def test_not_met_low_serverless():
    # 50 of 1000 → 5% → NOT_MET (< 15%)
    f = ProcessingServerlessComputeCheck().run(_Q, _ctx(1000.0, 50.0))
    assert f.verdict is Verdict.NOT_MET


def test_empty_usage_is_unknown_low():
    f = ProcessingServerlessComputeCheck().run(_Q, _ctx(0.0, 0.0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
