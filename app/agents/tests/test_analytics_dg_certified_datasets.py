from __future__ import annotations

from waf_agents.analytics.checks.dg_certified_datasets import CertifiedDatasetsCheck
from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-DG-01",
    pillar_id="data-ai-governance",
    title="Serve analytics from certified, cataloged datasets",
    principle="Analytics should consume certified, well-governed data",
)


def _ctx(total: int, certified: int) -> AgentContext:
    # Needles: 'total_uc_tables' matches _UC_TABLE_COUNT_SQL,
    #          'certified_tables' matches _CERTIFIED_SIGNAL_SQL.
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(
            {
                "total_uc_tables": [{"total_uc_tables": total}],
                "certified_tables": [{"certified_tables": certified}],
            }
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = CertifiedDatasetsCheck().run(_Q, _ctx(100, 25))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.25
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = CertifiedDatasetsCheck().run(_Q, _ctx(100, 8))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_not_met():
    f = CertifiedDatasetsCheck().run(_Q, _ctx(100, 2))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.HIGH


def test_empty_is_unknown_low():
    f = CertifiedDatasetsCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_score_rounded():
    f = CertifiedDatasetsCheck().run(_Q, _ctx(3, 1))
    assert f.score == round(1 / 3, 4)
