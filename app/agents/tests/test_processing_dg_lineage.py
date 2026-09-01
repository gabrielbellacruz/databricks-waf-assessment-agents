from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.dg_lineage import ProcessingLineageCheck

_Q = Question(
    id="PRO-DG-01",
    pillar_id="data-ai-governance",
    title="Capture lineage through transformation pipelines",
    principle="Govern data through transformations",
)

# FakeSqlClient matches on substrings:
#   "information_schema.tables"  -> total tables row
#   "source_table_full_name IS NOT NULL"  -> pipeline lineage row
def _ctx(total: int, with_lineage: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient(
            {
                "information_schema.tables": [{"total_tables": total}],
                "source_table_full_name IS NOT NULL": [
                    {"pipeline_lineage_tables": with_lineage}
                ],
            }
        ),
        catalogs=["main"],
    )


def test_met_high_lineage():
    # 70 of 100 → 70% → MET (threshold 60%)
    f = ProcessingLineageCheck().run(_Q, _ctx(100, 70))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.70
    assert f.sources


def test_partial_lineage():
    # 40 of 100 → 40% → PARTIAL (30–60%)
    f = ProcessingLineageCheck().run(_Q, _ctx(100, 40))
    assert f.verdict is Verdict.PARTIAL


def test_not_met_low_lineage():
    # 10 of 100 → 10% → NOT_MET (< 30%)
    f = ProcessingLineageCheck().run(_Q, _ctx(100, 10))
    assert f.verdict is Verdict.NOT_MET


def test_empty_tables_is_unknown_low():
    f = ProcessingLineageCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
