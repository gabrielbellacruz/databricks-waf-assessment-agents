"""Tests for WorkflowAuditCheck (ORC-DG-04)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.dg_audit import WorkflowAuditCheck

_Q = Question(
    id="ORC-DG-04",
    pillar_id="data-ai-governance",
    title="Audit workflow executions",
    principle="All workflow executions must be logged for compliance and debugging",
)


def _ctx(total: int, audited: int) -> AgentContext:
    return AgentContext(
        assessment_id="test-orc-dg-04",
        layer="orchestration",
        sql=FakeSqlClient(
            {
                # Matches _SQL_TOTAL (contains "total_jobs")
                "total_jobs": [{"total_jobs": total}],
                # Matches _SQL_AUDITED (contains "job_run_timeline")
                "job_run_timeline": [{"jobs_with_runs": audited}],
            }
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = WorkflowAuditCheck().run(_Q, _ctx(50, 45))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == round(45 / 50, 4)


def test_partial():
    f = WorkflowAuditCheck().run(_Q, _ctx(50, 25))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_not_met():
    f = WorkflowAuditCheck().run(_Q, _ctx(50, 10))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.HIGH


def test_empty_is_unknown_low():
    f = WorkflowAuditCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
    assert f.auto_assessable is True


def test_audited_clamped_to_total():
    # If run-timeline count exceeds total (race condition), score must not exceed 1.0
    f = WorkflowAuditCheck().run(_Q, _ctx(10, 15))
    assert f.score is not None
    assert f.score <= 1.0
    assert f.verdict is Verdict.MET


def test_collect_returns_one_evidence():
    ctx = _ctx(30, 25)
    ev = WorkflowAuditCheck().collect(ctx)
    assert len(ev) == 1
    assert ev[0].kind == "sql"


def test_collect_summary_reflects_counts():
    ctx = _ctx(30, 25)
    ev = WorkflowAuditCheck().collect(ctx)
    assert "25" in ev[0].summary
    assert "30" in ev[0].summary


def test_collect_rows_carry_counts():
    ctx = _ctx(40, 32)
    ev = WorkflowAuditCheck().collect(ctx)
    row = ev[0].rows[0]
    assert row["total_jobs"] == 40
    assert row["jobs_with_runs"] == 32
