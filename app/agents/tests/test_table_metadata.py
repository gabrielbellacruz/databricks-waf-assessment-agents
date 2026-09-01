from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.table_metadata import TableMetadataCheck

_Q = Question(
    id="STO-DG-02",
    pillar_id="data-ai-governance",
    title="Manage metadata and descriptions for stored tables",
    principle="Govern stored data with rich, discoverable metadata",
)


def _ctx(total: int, described: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(
            {"trim(comment)": [{"total": total, "described": described}]}
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = TableMetadataCheck().run(_Q, _ctx(100, 80))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.8
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = TableMetadataCheck().run(_Q, _ctx(100, 60))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_not_met():
    f = TableMetadataCheck().run(_Q, _ctx(100, 20))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.HIGH


def test_empty_is_unknown_low():
    f = TableMetadataCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
