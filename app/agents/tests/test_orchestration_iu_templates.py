"""Tests for WorkflowTemplatesCheck (ORC-IU-01)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.iu_templates import WorkflowTemplatesCheck

_Q = Question(
    id="ORC-IU-01",
    pillar_id="interoperability-usability",
    title="Use standard, reusable workflow templates",
    principle="Workflows should be built from shared, blessed templates",
)

# The check uses a single SQL with needle "distinct_name_prefixes"
_FAKE_ROWS = [{"total_jobs": 30, "distinct_name_prefixes": 5, "tagged_jobs": 25}]


def _ctx(*, llm_response: str | None = "", rows: list[dict] | None = None) -> AgentContext:
    return AgentContext(
        assessment_id="test-orc-iu-01",
        layer="orchestration",
        sql=FakeSqlClient(
            {"distinct_name_prefixes": rows if rows is not None else _FAKE_ROWS}
        ),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_two_evidences():
    ev = WorkflowTemplatesCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_kind():
    ev = WorkflowTemplatesCheck().collect(_ctx())
    assert ev[0].kind == "sql"


def test_collect_note_evidence():
    ev = WorkflowTemplatesCheck().collect(_ctx())
    assert ev[1].kind == "note"


def test_collect_summary_includes_total_and_tagged():
    ev = WorkflowTemplatesCheck().collect(_ctx())
    assert "30" in ev[0].summary
    assert "25" in ev[0].summary


def test_collect_summary_includes_distinct_prefixes():
    ev = WorkflowTemplatesCheck().collect(_ctx())
    assert "5" in ev[0].summary


def test_collect_rows_carry_data():
    ev = WorkflowTemplatesCheck().collect(_ctx())
    row = ev[0].rows[0]
    assert row["total_jobs"] == 30
    assert row["tagged_jobs"] == 25


def test_collect_empty_sql_result():
    ctx = AgentContext(
        assessment_id="test-orc-iu-01-empty",
        layer="orchestration",
        sql=FakeSqlClient(),
    )
    ev = WorkflowTemplatesCheck().collect(ctx)
    assert "0" in ev[0].summary


def test_judge_maps_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Some naming regularity but not fully templated"}'
    )
    f = WorkflowTemplatesCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Very consistent job naming"}'
    )
    f = WorkflowTemplatesCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = WorkflowTemplatesCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
