"""Tests for SchedulerIntegrationCheck (ORC-IU-05)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.iu_scheduler_integration import SchedulerIntegrationCheck

_Q = Question(
    id="ORC-IU-05",
    pillar_id="interoperability-usability",
    title="Integrate workflows with enterprise schedulers",
    principle="Databricks workflows should be callable from enterprise scheduling tools",
)

# Needles are distinct substrings:
#   "cron_scheduled"                  -> _SQL_TRIGGERS (SUM ... AS cron_scheduled)
#   "external_scheduler_candidates"   -> _SQL_EXTERNAL_CANDIDATES (AS external_scheduler_candidates)
_FAKE_RESPONSES = {
    "cron_scheduled": [
        {
            "total_jobs": 40,
            "cron_scheduled": 15,
            "file_arrival_triggered": 5,
            "periodic_triggered": 3,
            "unscheduled_jobs": 17,
        }
    ],
    "external_scheduler_candidates": [{"external_scheduler_candidates": 10}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="test-orc-iu-05",
        layer="orchestration",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidences():
    ev = SchedulerIntegrationCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_trigger_evidence_is_sql():
    ev = SchedulerIntegrationCheck().collect(_ctx())
    assert ev[0].kind == "sql"


def test_collect_candidates_evidence_is_sql():
    ev = SchedulerIntegrationCheck().collect(_ctx())
    assert ev[1].kind == "sql"


def test_collect_note_evidence():
    ev = SchedulerIntegrationCheck().collect(_ctx())
    assert ev[2].kind == "note"


def test_collect_trigger_summary_reflects_counts():
    ev = SchedulerIntegrationCheck().collect(_ctx())
    summary = ev[0].summary
    assert "40" in summary
    assert "15" in summary
    assert "17" in summary


def test_collect_candidates_summary_reflects_count():
    ev = SchedulerIntegrationCheck().collect(_ctx())
    assert "10" in ev[1].summary


def test_collect_trigger_rows_carry_data():
    ev = SchedulerIntegrationCheck().collect(_ctx())
    row = ev[0].rows[0]
    assert row["total_jobs"] == 40
    assert row["cron_scheduled"] == 15
    assert row["unscheduled_jobs"] == 17


def test_collect_candidates_rows_carry_data():
    ev = SchedulerIntegrationCheck().collect(_ctx())
    assert ev[1].rows[0]["external_scheduler_candidates"] == 10


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "low",'
        ' "score": null, "rationale": "Un-scheduled jobs with runs are possible'
        ' ext-scheduler targets"}'
    )
    f = SchedulerIntegrationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.sources


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Clear pattern of external scheduling"}'
    )
    f = SchedulerIntegrationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = SchedulerIntegrationCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
