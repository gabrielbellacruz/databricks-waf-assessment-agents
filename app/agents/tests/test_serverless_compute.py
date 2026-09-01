from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.serverless_compute import ServerlessComputeCheck

_Q = Question(
    id="ING-PE-04",
    pillar_id="performance-efficiency",
    title="Use serverless compute for ingestion where appropriate",
    principle="Right-size and modernise compute",
)


def _ctx(total: float, serverless: float) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient(
            {"system.billing.usage": [{"total_dbus": total, "serverless_dbus": serverless}]}
        ),
        catalogs=["main"],
    )


def test_met_medium_confidence():
    f = ServerlessComputeCheck().run(_Q, _ctx(100.0, 60.0))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.6
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = ServerlessComputeCheck().run(_Q, _ctx(100.0, 30.0))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_not_met():
    f = ServerlessComputeCheck().run(_Q, _ctx(100.0, 5.0))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_no_usage_is_unknown_low():
    f = ServerlessComputeCheck().run(_Q, _ctx(0.0, 0.0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_empty_rows_is_unknown_low():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient({}),
        catalogs=["main"],
    )
    f = ServerlessComputeCheck().run(_Q, ctx)
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
