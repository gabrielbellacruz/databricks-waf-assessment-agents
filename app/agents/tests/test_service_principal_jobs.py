from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.service_principal_jobs import ServicePrincipalJobsCheck

_Q = Question(
    id="ING-SCP-04",
    pillar_id="security-compliance-privacy",
    title="Run production ingestion jobs as service principals",
    principle="Secure access to data",
)


def _ctx(total: int, sp_jobs: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient({"system.lakeflow.jobs": [{"total": total, "sp_jobs": sp_jobs}]}),
        catalogs=["main"],
    )


def test_met_medium_confidence():
    f = ServicePrincipalJobsCheck().run(_Q, _ctx(100, 90))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.9
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = ServicePrincipalJobsCheck().run(_Q, _ctx(100, 60))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_not_met():
    f = ServicePrincipalJobsCheck().run(_Q, _ctx(100, 10))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_no_jobs_is_unknown_low():
    f = ServicePrincipalJobsCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
