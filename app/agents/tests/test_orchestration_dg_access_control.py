"""Tests for WorkflowAccessControlCheck (ORC-DG-03)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.dg_access_control import WorkflowAccessControlCheck

_Q = Question(
    id="ORC-DG-03",
    pillar_id="data-ai-governance",
    title="Control who can create, edit, and run workflows",
    principle="Workflow permissions must be explicitly governed",
)

# Needles are distinct, non-overlapping substrings of the two SQL strings:
#   "sp_jobs"    -> _SQL_SP  (SUM ... AS sp_jobs)
#   "tagged_jobs" -> _SQL_TAGS (SUM ... AS tagged_jobs)
_FAKE_RESPONSES = {
    "sp_jobs": [{"total_jobs": 40, "sp_jobs": 32}],
    "tagged_jobs": [{"total_jobs": 40, "tagged_jobs": 20}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="test-orc-dg-03",
        layer="orchestration",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidences():
    ev = WorkflowAccessControlCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_sp_evidence_is_sql():
    ev = WorkflowAccessControlCheck().collect(_ctx())
    assert ev[0].kind == "sql"


def test_collect_tags_evidence_is_sql():
    ev = WorkflowAccessControlCheck().collect(_ctx())
    assert ev[1].kind == "sql"


def test_collect_note_evidence():
    ev = WorkflowAccessControlCheck().collect(_ctx())
    assert ev[2].kind == "note"


def test_collect_sp_summary_reflects_counts():
    ev = WorkflowAccessControlCheck().collect(_ctx())
    assert "32" in ev[0].summary
    assert "40" in ev[0].summary


def test_collect_tags_summary_reflects_counts():
    ev = WorkflowAccessControlCheck().collect(_ctx())
    assert "20" in ev[1].summary


def test_judge_maps_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Some SP usage but ACLs not confirmed"}'
    )
    f = WorkflowAccessControlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Strong SP usage observed"}'
    )
    f = WorkflowAccessControlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = WorkflowAccessControlCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
