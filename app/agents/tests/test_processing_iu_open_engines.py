from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.iu_open_engines import ProcessingOpenEnginesCheck

_Q = Question(
    id="PRO-IU-02",
    pillar_id="interoperability-usability",
    title="Use open, standard processing engines",
    principle="Write transformation outputs to open, interoperable formats",
)

# SQL needle: "data_source_format"
def _ctx(total: int, open_fmt: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient(
            {"data_source_format": [{"total": total, "open_fmt": open_fmt}]}
        ),
        catalogs=["main"],
    )


def test_met_high_open_format():
    # 90 of 100 → 90% → MET (threshold 80%)
    f = ProcessingOpenEnginesCheck().run(_Q, _ctx(100, 90))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.90
    assert f.sources and f.sources[0].kind == "sql"


def test_partial_open_format():
    # 60 of 100 → 60% → PARTIAL (50–80%)
    f = ProcessingOpenEnginesCheck().run(_Q, _ctx(100, 60))
    assert f.verdict is Verdict.PARTIAL


def test_not_met_low_open_format():
    # 20 of 100 → 20% → NOT_MET (< 50%)
    f = ProcessingOpenEnginesCheck().run(_Q, _ctx(100, 20))
    assert f.verdict is Verdict.NOT_MET


def test_empty_tables_is_unknown_low():
    f = ProcessingOpenEnginesCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
