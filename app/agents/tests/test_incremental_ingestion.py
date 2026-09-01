"""Tests for IncrementalIngestionCheck (ING-PE-02)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.incremental_ingestion import IncrementalIngestionCheck

_Q = Question(
    id="ING-PE-02",
    pillar_id="performance-efficiency",
    title="Ingest incrementally rather than reprocessing full loads",
    principle="Optimize ingestion throughput and avoid wasted recompute",
)

# Canned system.query.history aggregate row: healthy mix of incremental patterns.
_ROWS = [
    {
        "autoloader": 10,
        "merge_stmts": 5,
        "copy_into": 3,
        "full_reload": 2,
        "total": 100,
    }
]


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient({"system.query.history": _ROWS}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence reflects the pattern counts
# ---------------------------------------------------------------------------


def test_collect_returns_one_sql_evidence():
    ev = IncrementalIngestionCheck().collect(_ctx())
    assert len(ev) == 1
    assert ev[0].kind == "sql"


def test_collect_summary_contains_incremental_counts():
    ev = IncrementalIngestionCheck().collect(_ctx())
    summary = ev[0].summary
    assert "autoloader=10" in summary
    assert "merge=5" in summary
    assert "copy_into=3" in summary


def test_collect_summary_contains_full_reload_count():
    ev = IncrementalIngestionCheck().collect(_ctx())
    # The anti-pattern count must appear in the summary for the LLM judge.
    assert "2" in ev[0].summary  # full_reload=2


def test_collect_rows_carry_all_counts():
    ev = IncrementalIngestionCheck().collect(_ctx())
    row = ev[0].rows[0]
    assert row["autoloader"] == 10
    assert row["merge_stmts"] == 5
    assert row["copy_into"] == 3
    assert row["full_reload"] == 2
    assert row["total"] == 100


def test_collect_ref_points_to_ingestion_docs():
    ev = IncrementalIngestionCheck().collect(_ctx())
    assert ev[0].ref == "https://docs.databricks.com/en/ingestion/index.html"


def test_collect_no_rows_still_returns_evidence():
    """An empty query result degrades gracefully rather than crashing."""
    ctx = AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient(),  # no canned rows
        catalogs=["main"],
    )
    ev = IncrementalIngestionCheck().collect(ctx)
    assert len(ev) == 1
    assert ev[0].kind == "sql"
    assert ev[0].rows == []


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_maps_llm_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "mostly incremental"}'
    )
    f = IncrementalIngestionCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_high_confidence_to_medium():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "some full reloads present"}'
    )
    f = IncrementalIngestionCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM-judged checks are capped at medium even when the model claims high.
    assert f.confidence is Confidence.MEDIUM


def test_judge_attaches_evidence_for_explainability():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "full-reload dominates"}'
    )
    f = IncrementalIngestionCheck().run(_Q, _ctx(llm_response=resp))
    assert f.sources


# ---------------------------------------------------------------------------
# llm=None — unassessed fallback
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = IncrementalIngestionCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached
