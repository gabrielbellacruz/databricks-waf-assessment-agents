from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.dg_transformation_docs import (
    ProcessingTransformationDocsCheck,
)

_Q = Question(
    id="PRO-DG-03",
    pillar_id="data-ai-governance",
    title="Document transformation logic and business rules",
    principle="Maintain clear documentation of transformation intent",
)

# SQL needle: "comment IS NOT NULL"
def _ctx(total: int, documented: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient(
            {"comment IS NOT NULL": [{"total": total, "documented": documented}]}
        ),
        catalogs=["main"],
    )


def test_met_high_documentation():
    # 60 of 100 → 60% → MET (threshold 50%)
    f = ProcessingTransformationDocsCheck().run(_Q, _ctx(100, 60))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.60
    assert f.sources and f.sources[0].kind == "sql"


def test_partial_documentation():
    # 30 of 100 → 30% → PARTIAL (20–50%)
    f = ProcessingTransformationDocsCheck().run(_Q, _ctx(100, 30))
    assert f.verdict is Verdict.PARTIAL


def test_not_met_low_documentation():
    # 5 of 100 → 5% → NOT_MET (< 20%)
    f = ProcessingTransformationDocsCheck().run(_Q, _ctx(100, 5))
    assert f.verdict is Verdict.NOT_MET


def test_empty_tables_is_unknown_low():
    f = ProcessingTransformationDocsCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
