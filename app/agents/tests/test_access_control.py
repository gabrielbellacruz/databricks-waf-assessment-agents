from __future__ import annotations

from waf_agents.core.clients import (
    AgentContext,
    FakeLlmClient,
    FakeSqlClient,
)
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.access_control import AccessControlCheck

_Q = Question(
    id="ING-DG-04",
    pillar_id="governance",
    title="Centralize access control for landing zones and ingestion pipelines",
    principle="Apply least-privilege and centralized access control",
)

_ROWS = [{"total_grants": 120, "user_grants": 30, "group_grants": 90}]


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient({"table_privileges": _ROWS}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_evidence_summary_reflects_counts():
    ev = AccessControlCheck().collect(_ctx())
    assert len(ev) == 1
    e = ev[0]
    assert e.kind == "sql"
    # Summary must mention both the group count and the individual-user count.
    assert "90" in e.summary and "30" in e.summary
    assert e.rows == [{"total_grants": 120, "user_grants": 30, "group_grants": 90}]
    assert e.ref and "unity-catalog" in e.ref


def test_collect_empty_rows_returns_no_grants_evidence():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient({}),
        catalogs=["main"],
        llm=FakeLlmClient(""),
    )
    ev = AccessControlCheck().collect(ctx)
    assert len(ev) == 1
    assert "No table grants" in ev[0].summary
    assert ev[0].rows == []


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null, '
        '"rationale": "Most grants are to groups, but 30 individual-user grants remain."}'
    )
    f = AccessControlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # judge_with_llm caps LLM-claimed 'high' down to 'medium'
    assert f.confidence is Confidence.MEDIUM
    assert f.sources  # evidence attached for explainability


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium", "score": null, '
        '"rationale": "All grants go to groups or service principals."}'
    )
    f = AccessControlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = AccessControlCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still collected and attached even without an LLM
    assert f.sources
    assert f.sources[0].kind == "sql"
