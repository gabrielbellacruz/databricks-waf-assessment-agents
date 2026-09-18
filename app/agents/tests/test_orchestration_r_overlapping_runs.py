from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.r_overlapping_runs import OrcOverlappingRunsCheck

_Q = Question(
    id="ORC-R-04",
    pillar_id="reliability",
    title="Prevent overlapping runs of the same workflow",
    principle="Design for failure and recovery",
)


def _ctx(total: int, protected: int) -> AgentContext:
    return AgentContext(
        assessment_id="test-orc",
        layer="orchestration",
        sql=FakeSqlClient(
            {"prev_max_end": [{"total_jobs": total, "protected_jobs": protected}]}
        ),
        catalogs=["main"],
    )


# --- deterministic verdicts ---

def test_met_medium_confidence():
    # 9 of 10 protected = 90% >= MET threshold (90%)
    f = OrcOverlappingRunsCheck().run(_Q, _ctx(10, 9))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.9


def test_met_all_protected():
    f = OrcOverlappingRunsCheck().run(_Q, _ctx(5, 5))
    assert f.verdict is Verdict.MET
    assert f.score == 1.0


def test_partial():
    # 8 of 10 = 80% — between 70% (PARTIAL threshold) and 90% (MET threshold)
    f = OrcOverlappingRunsCheck().run(_Q, _ctx(10, 8))
    assert f.verdict is Verdict.PARTIAL


def test_not_met():
    # 5 of 10 = 50% — below 70% PARTIAL threshold
    f = OrcOverlappingRunsCheck().run(_Q, _ctx(10, 5))
    assert f.verdict is Verdict.NOT_MET


def test_empty_is_unknown_low():
    f = OrcOverlappingRunsCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


# --- evidence ---

def test_collect_evidence_has_rows():
    ev = OrcOverlappingRunsCheck().collect(_ctx(10, 9))
    assert ev[0].kind == "sql"
    assert ev[0].rows[0]["total_jobs"] == 10
    assert ev[0].rows[0]["protected_jobs"] == 9


def test_rationale_mentions_unprotected_jobs():
    f = OrcOverlappingRunsCheck().run(_Q, _ctx(10, 8))
    assert "2" in f.rationale  # 10 - 8 = 2 unprotected
