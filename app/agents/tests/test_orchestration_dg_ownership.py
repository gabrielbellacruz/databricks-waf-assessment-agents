"""Tests for WorkflowOwnershipCheck (ORC-DG-01)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.dg_ownership import WorkflowOwnershipCheck

_Q = Question(
    id="ORC-DG-01",
    pillar_id="data-ai-governance",
    title="Assign clear ownership to every workflow",
    principle="Every workflow must have an explicit owner for accountability",
)


def _ctx(total: int, owned: int) -> AgentContext:
    return AgentContext(
        assessment_id="test-orc-dg-01",
        layer="orchestration",
        sql=FakeSqlClient(
            {"run_as IS NOT NULL": [{"total_jobs": total, "owned_jobs": owned}]}
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = WorkflowOwnershipCheck().run(_Q, _ctx(100, 95))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.95
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = WorkflowOwnershipCheck().run(_Q, _ctx(100, 70))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_not_met():
    f = WorkflowOwnershipCheck().run(_Q, _ctx(100, 30))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.HIGH


def test_empty_is_unknown_low():
    f = WorkflowOwnershipCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
    assert f.auto_assessable is True


def test_score_is_rounded_ratio():
    f = WorkflowOwnershipCheck().run(_Q, _ctx(3, 2))
    assert f.score == round(2 / 3, 4)


def test_collect_sql_evidence_kind():
    ctx = _ctx(10, 8)
    ev = WorkflowOwnershipCheck().collect(ctx)
    assert len(ev) == 1
    assert ev[0].kind == "sql"


def test_collect_summary_reflects_counts():
    ctx = _ctx(50, 45)
    ev = WorkflowOwnershipCheck().collect(ctx)
    assert "45" in ev[0].summary
    assert "50" in ev[0].summary


def test_collect_rows_contain_counts():
    ctx = _ctx(20, 18)
    ev = WorkflowOwnershipCheck().collect(ctx)
    row = ev[0].rows[0]
    assert row["total_jobs"] == 20
    assert row["owned_jobs"] == 18
