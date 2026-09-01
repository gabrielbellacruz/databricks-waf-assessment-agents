from __future__ import annotations

from waf_agents.analytics.checks.pe_serverless_warehouses import ServerlessWarehousesCheck
from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-PE-01",
    pillar_id="performance-efficiency",
    title="Use serverless SQL warehouses for fast startup",
    principle="Minimize cold-start latency for analytics users",
)


def _ctx(total: int, serverless_count: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(
            {"serverless_count": [{"total": total, "serverless_count": serverless_count}]}
        ),
    )


def test_met_high_confidence():
    f = ServerlessWarehousesCheck().run(_Q, _ctx(4, 3))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.75


def test_partial():
    f = ServerlessWarehousesCheck().run(_Q, _ctx(10, 2))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_not_met():
    f = ServerlessWarehousesCheck().run(_Q, _ctx(10, 1))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.HIGH


def test_empty_is_unknown_low():
    f = ServerlessWarehousesCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_score_at_met_boundary():
    # exactly 50% -> MET
    f = ServerlessWarehousesCheck().run(_Q, _ctx(2, 1))
    assert f.verdict is Verdict.MET
    assert f.score == 0.5


def test_evidence_has_sql_kind():
    f = ServerlessWarehousesCheck().run(_Q, _ctx(6, 4))
    assert f.sources[0].kind == "sql"
    assert f.sources[0].rows[0]["total"] == 6
    assert f.sources[0].rows[0]["serverless_count"] == 4
