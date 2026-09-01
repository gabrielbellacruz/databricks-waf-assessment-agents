from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.delta_storage import DeltaStorageCheck

_Q = Question(
    id="STO-IU-01",
    pillar_id="interoperability-usability",
    title="Store data in Delta Lake",
    principle="Use Delta Lake as the default storage format",
)


def _ctx(total: int, delta_count: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(
            {"information_schema.tables": [{"total": total, "delta_count": delta_count}]}
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = DeltaStorageCheck().run(_Q, _ctx(100, 95))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.95
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = DeltaStorageCheck().run(_Q, _ctx(100, 70))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_not_met():
    f = DeltaStorageCheck().run(_Q, _ctx(100, 20))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.HIGH


def test_empty_is_unknown_low():
    f = DeltaStorageCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
    assert f.auto_assessable is True
