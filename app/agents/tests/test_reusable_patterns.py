from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.reusable_patterns import ReusablePatternsCheck

_Q = Question(
    id="ING-IU-02",
    pillar_id="interoperability-usability",
    title="Use standard, reusable ingestion patterns",
    principle="Prefer standard, shareable ingestion building blocks",
)

_SQL_ROWS = [{"total_jobs": 30, "distinct_name_prefixes": 4, "tagged_jobs": 25}]


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient({"system.lakeflow.jobs": _SQL_ROWS}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_produces_sql_and_note_evidence():
    ev = ReusablePatternsCheck().collect(_ctx())
    kinds = [e.kind for e in ev]
    assert "sql" in kinds
    assert "note" in kinds
    assert len(ev) == 2


def test_collect_sql_evidence_summarises_job_stats():
    ev = ReusablePatternsCheck().collect(_ctx())
    sql_ev = next(e for e in ev if e.kind == "sql")
    assert "30" in sql_ev.summary  # total_jobs reflected in summary
    assert sql_ev.rows  # data row attached for explainability


def test_collect_note_evidence_has_no_rows():
    ev = ReusablePatternsCheck().collect(_ctx())
    note_ev = next(e for e in ev if e.kind == "note")
    assert note_ev.rows == []


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "low prefix ratio suggests one-off jobs"}'
    )
    f = ReusablePatternsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM  # high is capped to medium for LLM checks
    assert f.sources  # evidence attached for explainability


def test_no_llm_degrades_to_unassessed():
    f = ReusablePatternsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached even without LLM
