"""Tests for ServerlessOrchestrationCheck (ORC-IU-04)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.iu_serverless import ServerlessOrchestrationCheck

_Q = Question(
    id="ORC-IU-04",
    pillar_id="interoperability-usability",
    title="Use serverless for orchestrated tasks where suitable",
    principle="Serverless compute eliminates cluster management overhead",
)


def _ctx(total: float, serverless: float) -> AgentContext:
    return AgentContext(
        assessment_id="test-orc-iu-04",
        layer="orchestration",
        sql=FakeSqlClient(
            {"SERVERLESS": [{"total_dbus": total, "serverless_dbus": serverless}]}
        ),
        catalogs=["main"],
    )


def test_met_medium_confidence():
    f = ServerlessOrchestrationCheck().run(_Q, _ctx(100.0, 60.0))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == round(60.0 / 100.0, 4)


def test_partial():
    f = ServerlessOrchestrationCheck().run(_Q, _ctx(100.0, 20.0))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_not_met():
    f = ServerlessOrchestrationCheck().run(_Q, _ctx(100.0, 5.0))
    assert f.verdict is Verdict.NOT_MET


def test_empty_is_unknown_low():
    f = ServerlessOrchestrationCheck().run(_Q, _ctx(0.0, 0.0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
    assert f.auto_assessable is True


def test_collect_returns_one_evidence():
    ctx = _ctx(200.0, 110.0)
    ev = ServerlessOrchestrationCheck().collect(ctx)
    assert len(ev) == 1
    assert ev[0].kind == "sql"


def test_collect_summary_reflects_dbus():
    ctx = _ctx(200.0, 110.0)
    ev = ServerlessOrchestrationCheck().collect(ctx)
    assert "110.00" in ev[0].summary
    assert "200.00" in ev[0].summary


def test_collect_rows_carry_dbus():
    ctx = _ctx(50.0, 25.0)
    ev = ServerlessOrchestrationCheck().collect(ctx)
    row = ev[0].rows[0]
    assert row["total_dbus"] == 50.0
    assert row["serverless_dbus"] == 25.0
