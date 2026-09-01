from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.lineage_coverage import LineageCoverageCheck

_Q = Question(
    id="ING-DG-02",
    pillar_id="governance",
    title="Capture lineage from source systems into the lakehouse",
    principle="Govern data end-to-end",
)


def _ctx(total: int, with_lineage: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient({"table_lineage": [{"total": total, "with_lineage": with_lineage}]}),
        catalogs=["main"],
    )


def test_met_medium_confidence():
    f = LineageCoverageCheck().run(_Q, _ctx(100, 65))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.65
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = LineageCoverageCheck().run(_Q, _ctx(100, 40))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_not_met():
    f = LineageCoverageCheck().run(_Q, _ctx(100, 10))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_no_tables_is_unknown_low():
    f = LineageCoverageCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
