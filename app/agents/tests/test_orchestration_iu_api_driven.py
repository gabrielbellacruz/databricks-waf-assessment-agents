"""Tests for ApiDrivenOrchestrationCheck (ORC-IU-03)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.iu_api_driven import ApiDrivenOrchestrationCheck

_Q = Question(
    id="ORC-IU-03",
    pillar_id="interoperability-usability",
    title="Orchestrate via open, API-driven interfaces",
    principle="Workflows should be triggerable and manageable via standard APIs",
)

# Needles are distinct substrings:
#   "file_arrival_jobs"  -> _SQL_TRIGGERS (SUM ... AS file_arrival_jobs)
#   "api_owners"         -> _SQL_API_OWNERS (AS api_owners)
_FAKE_RESPONSES = {
    "file_arrival_jobs": [
        {
            "total_jobs": 60,
            "cron_jobs": 20,
            "file_arrival_jobs": 15,
            "periodic_jobs": 5,
        }
    ],
    "api_owners": [{"api_owners": 8}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="test-orc-iu-03",
        layer="orchestration",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidences():
    ev = ApiDrivenOrchestrationCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_trigger_evidence_is_sql():
    ev = ApiDrivenOrchestrationCheck().collect(_ctx())
    assert ev[0].kind == "sql"


def test_collect_api_owners_evidence_is_sql():
    ev = ApiDrivenOrchestrationCheck().collect(_ctx())
    assert ev[1].kind == "sql"


def test_collect_note_evidence():
    ev = ApiDrivenOrchestrationCheck().collect(_ctx())
    assert ev[2].kind == "note"


def test_collect_trigger_summary_reflects_counts():
    ev = ApiDrivenOrchestrationCheck().collect(_ctx())
    summary = ev[0].summary
    assert "60" in summary
    assert "20" in summary
    assert "15" in summary
    assert "5" in summary


def test_collect_api_owners_summary_reflects_count():
    ev = ApiDrivenOrchestrationCheck().collect(_ctx())
    assert "8" in ev[1].summary


def test_collect_trigger_rows_carry_data():
    ev = ApiDrivenOrchestrationCheck().collect(_ctx())
    row = ev[0].rows[0]
    assert row["total_jobs"] == 60
    assert row["cron_jobs"] == 20
    assert row["file_arrival_jobs"] == 15
    assert row["periodic_jobs"] == 5


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Mix of trigger types but unclear API usage"}'
    )
    f = ApiDrivenOrchestrationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Strong SP and diverse triggers"}'
    )
    f = ApiDrivenOrchestrationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = ApiDrivenOrchestrationCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
