from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.pe_shared_compute import OrcSharedComputeCheck

_Q = Question(
    id="ORC-PE-02",
    pillar_id="performance-efficiency",
    title="Reuse compute across workflow tasks",
    principle="Optimize performance through efficient resource use",
)


def _ctx(total: int, shared: int) -> AgentContext:
    return AgentContext(
        assessment_id="test-orc",
        layer="orchestration",
        sql=FakeSqlClient(
            {
                "job_task_run_timeline": [
                    {"total_multi_task_runs": total, "shared_compute_runs": shared}
                ]
            }
        ),
        catalogs=["main"],
    )


# --- deterministic verdicts ---

def test_met_medium_confidence():
    # 7 of 10 = 70% >= MET threshold (60%)
    f = OrcSharedComputeCheck().run(_Q, _ctx(10, 7))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.7


def test_met_all_shared():
    f = OrcSharedComputeCheck().run(_Q, _ctx(5, 5))
    assert f.verdict is Verdict.MET
    assert f.score == 1.0


def test_partial():
    # 4 of 10 = 40% — between 30% (PARTIAL) and 60% (MET)
    f = OrcSharedComputeCheck().run(_Q, _ctx(10, 4))
    assert f.verdict is Verdict.PARTIAL


def test_not_met():
    # 2 of 10 = 20% — below 30% PARTIAL threshold
    f = OrcSharedComputeCheck().run(_Q, _ctx(10, 2))
    assert f.verdict is Verdict.NOT_MET


def test_empty_is_unknown_low():
    f = OrcSharedComputeCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


# --- evidence ---

def test_collect_evidence_has_rows():
    ev = OrcSharedComputeCheck().collect(_ctx(10, 7))
    assert ev[0].kind == "sql"
    assert ev[0].rows[0]["total_multi_task_runs"] == 10
    assert ev[0].rows[0]["shared_compute_runs"] == 7


def test_collect_summary_mentions_shared_clusters():
    ev = OrcSharedComputeCheck().collect(_ctx(10, 7))
    assert "shared" in ev[0].summary.lower() or "reused" in ev[0].summary.lower()


def test_rationale_mentions_proxy_limitation():
    f = OrcSharedComputeCheck().run(_Q, _ctx(10, 7))
    assert "serverless" in f.rationale.lower()
