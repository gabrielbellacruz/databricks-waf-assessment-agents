from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.scp_service_principal import OrcServicePrincipalCheck

_Q = Question(
    id="ORC-SCP-01",
    pillar_id="scp",
    title="Run production workflows as service principals",
    principle="Use service principals for non-interactive workloads",
)


def _ctx(total: int, sp_jobs: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient(
            {"run_as NOT LIKE '%@%'": [{"total": total, "sp_jobs": sp_jobs}]}
        ),
        catalogs=[],
    )


def test_met_medium_confidence():
    f = OrcServicePrincipalCheck().run(_Q, _ctx(100, 95))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.95


def test_partial():
    f = OrcServicePrincipalCheck().run(_Q, _ctx(100, 70))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_not_met():
    f = OrcServicePrincipalCheck().run(_Q, _ctx(100, 20))
    assert f.verdict is Verdict.NOT_MET


def test_empty_is_unknown_low():
    f = OrcServicePrincipalCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_evidence_has_sql_kind():
    f = OrcServicePrincipalCheck().run(_Q, _ctx(50, 45))
    assert f.sources[0].kind == "sql"
    assert f.sources[0].rows[0]["total"] == 50
    assert f.sources[0].rows[0]["sp_jobs"] == 45
