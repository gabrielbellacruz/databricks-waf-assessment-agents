from __future__ import annotations

from waf_agents.analytics.checks.co_serverless_sql import ServerlessSqlCheck
from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-CO-03",
    pillar_id="cost-optimization",
    title="Prefer serverless for spiky analytics demand",
    principle="Match compute to demand characteristics",
)


def _ctx(total: float, serverless: float) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(
            {
                "total_sql_dbus": [
                    {"total_sql_dbus": total, "serverless_dbus": serverless}
                ]
            }
        ),
        catalogs=["main"],
    )


def test_met_medium_confidence():
    f = ServerlessSqlCheck().run(_Q, _ctx(100.0, 60.0))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.6
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = ServerlessSqlCheck().run(_Q, _ctx(100.0, 20.0))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_not_met():
    f = ServerlessSqlCheck().run(_Q, _ctx(100.0, 5.0))
    assert f.verdict is Verdict.NOT_MET
    assert f.score == 0.05


def test_no_usage_is_unknown_low():
    f = ServerlessSqlCheck().run(_Q, _ctx(0.0, 0.0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
