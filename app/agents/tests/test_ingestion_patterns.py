"""Tests for IngestionPatternsCheck (ING-PE-01).

Covers:
  - collect() always produces exactly two Evidence entries (sql + note)
  - sql evidence carries the expected distribution rows and SQL detail
  - judge() maps an LLM verdict correctly and caps confidence at medium
  - no LLM wired -> unassessed finding with evidence still attached
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.ingestion_patterns import IngestionPatternsCheck

_Q = Question(
    id="ING-PE-01",
    pillar_id="performance-efficiency",
    title="Understand your ingestion patterns and access needs",
    principle="Select appropriate ingestion patterns for each source",
)

_SQL_ROWS = [
    {
        "total_jobs": 10,
        "continuous": 2,
        "periodic": 5,
        "file_arrival": 2,
        "untriggered": 1,
    }
]


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient({"system.lakeflow.jobs": _SQL_ROWS}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_produces_two_evidence_entries():
    ev = IngestionPatternsCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    assert ev[1].kind == "note"


def test_collect_sql_evidence_has_distribution():
    ev = IngestionPatternsCheck().collect(_ctx())
    assert ev[0].rows == [
        {
            "total_jobs": 10,
            "continuous": 2,
            "periodic": 5,
            "file_arrival": 2,
            "untriggered": 1,
        }
    ]
    assert "system.lakeflow.jobs" in ev[0].detail


def test_collect_note_evidence_is_present():
    ev = IngestionPatternsCheck().collect(_ctx())
    assert ev[1].rows == []
    assert "organizational practice" in ev[1].summary


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "mixed trigger modes"}'
    )
    f = IngestionPatternsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources  # evidence attached for explainability


def test_no_llm_degrades_to_unassessed():
    f = IngestionPatternsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached even with no LLM
