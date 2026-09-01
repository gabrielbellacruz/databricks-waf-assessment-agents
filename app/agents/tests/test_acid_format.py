from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.acid_format import AcidFormatCheck

_Q = Question(
    id="STO-R-01",
    pillar_id="reliability",
    title="Use a storage format that supports ACID transactions",
    principle="Ensure data integrity through ACID-compliant storage",
)


def _ctx(total: int, acid_count: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(
            {"information_schema.tables": [{"total": total, "acid_count": acid_count}]}
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = AcidFormatCheck().run(_Q, _ctx(100, 92))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.92
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = AcidFormatCheck().run(_Q, _ctx(100, 75))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_not_met():
    f = AcidFormatCheck().run(_Q, _ctx(100, 30))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.HIGH


def test_empty_is_unknown_low():
    f = AcidFormatCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
    assert f.auto_assessable is True
