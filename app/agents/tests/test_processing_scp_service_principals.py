from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.scp_service_principals import ServicePrincipalJobsCheck

_Q = Question(
    id="PRO-SCP-01",
    pillar_id="security-compliance-privacy",
    title="Run transformation jobs as service principals",
    principle="Use non-human identities for production transformation jobs",
)


def _ctx(total: int, sp_jobs: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient({
            "run_as": [{"total": total, "sp_jobs": sp_jobs}],
        }),
        catalogs=["main"],
    )


def test_met_high_sp_ratio():
    # 95 of 100 -> 95% -> MET (>= 0.90)
    f = ServicePrincipalJobsCheck().run(_Q, _ctx(100, 95))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.95


def test_partial():
    # 60 of 100 -> 60% -> PARTIAL (>= 0.50, < 0.90)
    f = ServicePrincipalJobsCheck().run(_Q, _ctx(100, 60))
    assert f.verdict is Verdict.PARTIAL


def test_not_met_low_ratio():
    # 20 of 100 -> 20% -> NOT_MET
    f = ServicePrincipalJobsCheck().run(_Q, _ctx(100, 20))
    assert f.verdict is Verdict.NOT_MET


def test_empty_is_unknown_low():
    f = ServicePrincipalJobsCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_all_sp_is_met():
    f = ServicePrincipalJobsCheck().run(_Q, _ctx(10, 10))
    assert f.verdict is Verdict.MET
    assert f.score == 1.0


def test_collect_evidence_has_rows():
    ev = ServicePrincipalJobsCheck().collect(_ctx(50, 40))
    assert ev[0].kind == "sql"
    assert ev[0].rows[0]["total"] == 50
    assert ev[0].rows[0]["sp_jobs"] == 40
    assert "40 of 50" in ev[0].summary
