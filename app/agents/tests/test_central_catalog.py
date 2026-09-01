from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.central_catalog import CentralCatalogCheck

_Q = Question(
    id="STO-IU-04",
    pillar_id="interoperability-usability",
    title="Use a central catalog for discovery of stored data",
    principle="Make stored data discoverable through a central catalog",
)


def _ctx(total: int, governed: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(
            {"governed": [{"total": total, "governed": governed}]}
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = CentralCatalogCheck().run(_Q, _ctx(100, 95))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.95
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = CentralCatalogCheck().run(_Q, _ctx(100, 70))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_not_met():
    f = CentralCatalogCheck().run(_Q, _ctx(100, 30))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.HIGH


def test_empty_is_unknown_low():
    f = CentralCatalogCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
