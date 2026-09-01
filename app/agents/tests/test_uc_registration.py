from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.uc_registration import UcRegistrationCheck

_Q = Question(
    id="ING-DG-01",
    pillar_id="governance",
    title="Register ingested data in Unity Catalog at the point of entry",
    principle="Govern data at the point of entry",
)


def _ctx(total: int, legacy: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient(
            {"information_schema.tables": [{"total": total, "legacy": legacy}]}
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = UcRegistrationCheck().run(_Q, _ctx(100, 5))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.95
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = UcRegistrationCheck().run(_Q, _ctx(100, 30))
    assert f.verdict is Verdict.PARTIAL


def test_not_met():
    f = UcRegistrationCheck().run(_Q, _ctx(100, 70))
    assert f.verdict is Verdict.NOT_MET


def test_empty_is_unknown_low():
    f = UcRegistrationCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
