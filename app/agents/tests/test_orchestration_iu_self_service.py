"""Tests for SelfServiceSchedulingCheck (ORC-IU-02)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.iu_self_service import SelfServiceSchedulingCheck

_Q = Question(
    id="ORC-IU-02",
    pillar_id="interoperability-usability",
    title="Provide self-service scheduling for teams",
    principle="Teams should be able to create and own their own schedules",
)

# Needles are distinct substrings:
#   "scheduled_jobs"    -> _SQL_JOBS (SUM ... AS scheduled_jobs)
#   "active_pipelines"  -> _SQL_PIPELINES (AS active_pipelines)
_FAKE_RESPONSES = {
    "scheduled_jobs": [{"total_jobs": 50, "scheduled_jobs": 30, "distinct_owners": 12}],
    "active_pipelines": [{"active_pipelines": 8}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="test-orc-iu-02",
        layer="orchestration",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidences():
    ev = SelfServiceSchedulingCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_jobs_evidence_is_sql():
    ev = SelfServiceSchedulingCheck().collect(_ctx())
    assert ev[0].kind == "sql"


def test_collect_pipelines_evidence_is_sql():
    ev = SelfServiceSchedulingCheck().collect(_ctx())
    assert ev[1].kind == "sql"


def test_collect_note_evidence():
    ev = SelfServiceSchedulingCheck().collect(_ctx())
    assert ev[2].kind == "note"


def test_collect_jobs_summary_reflects_counts():
    ev = SelfServiceSchedulingCheck().collect(_ctx())
    assert "30" in ev[0].summary
    assert "50" in ev[0].summary
    assert "12" in ev[0].summary


def test_collect_pipelines_summary_reflects_count():
    ev = SelfServiceSchedulingCheck().collect(_ctx())
    assert "8" in ev[1].summary


def test_collect_rows_carry_data():
    ev = SelfServiceSchedulingCheck().collect(_ctx())
    row = ev[0].rows[0]
    assert row["total_jobs"] == 50
    assert row["scheduled_jobs"] == 30
    assert row["distinct_owners"] == 12
    assert ev[1].rows[0]["active_pipelines"] == 8


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "low",'
        ' "score": null, "rationale": "Some scheduled jobs but no self-service platform visible"}'
    )
    f = SelfServiceSchedulingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.sources


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Many owners with schedules"}'
    )
    f = SelfServiceSchedulingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = SelfServiceSchedulingCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
