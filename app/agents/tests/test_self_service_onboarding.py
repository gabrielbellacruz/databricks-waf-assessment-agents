"""Tests for SelfServiceOnboardingCheck (ING-IU-05)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.self_service_onboarding import SelfServiceOnboardingCheck

_Q = Question(
    id="ING-IU-05",
    pillar_id="interoperability-usability",
    title="Offer a self-service path to onboard new sources",
    principle="Enable self-service data onboarding",
)


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient(
            {
                "system.lakeflow.pipelines": [{"pipelines": 12}],
                "system.lakeflow.jobs": [{"jobs": 7}],
            }
        ),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_produces_sql_and_note_evidence():
    ev = SelfServiceOnboardingCheck().collect(_ctx())
    kinds = [e.kind for e in ev]
    assert "sql" in kinds
    assert "note" in kinds


def test_collect_note_present():
    ev = SelfServiceOnboardingCheck().collect(_ctx())
    notes = [e for e in ev if e.kind == "note"]
    assert notes, "expected at least one note evidence entry"


def test_collect_sql_includes_counts():
    ev = SelfServiceOnboardingCheck().collect(_ctx())
    sql_ev = next(e for e in ev if e.kind == "sql")
    assert "12" in sql_ev.summary
    assert "7" in sql_ev.summary


def test_collect_sql_rows_contain_both_counts():
    ev = SelfServiceOnboardingCheck().collect(_ctx())
    sql_ev = next(e for e in ev if e.kind == "sql")
    assert sql_ev.rows == [{"pipelines": 12, "jobs": 7}]


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "unknown", "confidence": "high", "score": null,'
        ' "rationale": "not observable from system tables"}'
    )
    f = SelfServiceOnboardingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN
    # LLM-claimed high confidence is capped at medium
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_maps_low_confidence_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "low", "score": null,'
        ' "rationale": "many pipelines but no self-service signal"}'
    )
    f = SelfServiceOnboardingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.LOW


def test_no_llm_degrades_to_unassessed():
    f = SelfServiceOnboardingCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached even without an LLM
