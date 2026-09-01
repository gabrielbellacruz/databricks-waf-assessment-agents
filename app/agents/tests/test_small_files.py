from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.small_files import SmallFilesCheck

_Q = Question(
    id="ING-PE-03",
    pillar_id="performance-efficiency",
    title="Avoid the small-file problem at the landing layer",
    principle="Optimize data layout for query performance",
)

# Canned SQL rows: 80 tables total, 60 Delta.
_SQL_ROWS = [{"total_tables": 80, "delta_tables": 60}]

_LLM_UNKNOWN = (
    '{"verdict": "unknown", "confidence": "low", "score": null,'
    ' "rationale": "No direct file-count evidence; Delta share is a weak proxy."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "medium", "score": null,'
    ' "rationale": "High Delta adoption suggests compaction tooling is available."}'
)


def _ctx(
    *, llm_response: str | None = _LLM_UNKNOWN, sql_rows: list[dict] | None = None
) -> AgentContext:
    rows = _SQL_ROWS if sql_rows is None else sql_rows
    return AgentContext(
        assessment_id="test-a1",
        layer="ingestion",
        sql=FakeSqlClient({"information_schema.tables": rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_two_evidence_entries():
    ev = SmallFilesCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_kind_and_content():
    ev = SmallFilesCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert "60 of 80" in sql_ev.summary
    assert sql_ev.rows[0]["total_tables"] == 80
    assert sql_ev.rows[0]["delta_tables"] == 60
    assert sql_ev.rows[0]["delta_pct"] == 75.0


def test_collect_note_evidence_is_present():
    ev = SmallFilesCheck().collect(_ctx())
    note_ev = ev[1]
    assert note_ev.kind == "note"
    assert note_ev.rows == []
    assert note_ev.ref == "https://docs.databricks.com/en/delta/optimize.html"


def test_collect_note_summary_mentions_measurement_gap():
    ev = SmallFilesCheck().collect(_ctx())
    summary_lower = ev[1].summary.lower()
    assert "file-size" in summary_lower or "small-file" in summary_lower


def test_collect_no_rows_handles_gracefully():
    ev = SmallFilesCheck().collect(_ctx(sql_rows=[]))
    assert ev[0].rows[0]["total_tables"] == 0
    assert ev[0].rows[0]["delta_tables"] == 0
    assert "No managed" in ev[0].summary


def test_collect_zero_row_result_is_handled():
    """FakeSqlClient returns [] when no needle matches; must not raise."""
    ctx = AgentContext(
        assessment_id="t2",
        layer="ingestion",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = SmallFilesCheck().collect(ctx)
    assert ev[0].rows[0]["total_tables"] == 0


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_unknown_verdict_mapped():
    f = SmallFilesCheck().run(_Q, _ctx(llm_response=_LLM_UNKNOWN))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
    assert f.sources


def test_judge_partial_verdict_mapped():
    f = SmallFilesCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_confidence_capped_at_medium_when_llm_claims_high():
    high_conf = (
        '{"verdict": "unknown", "confidence": "high", "score": null,'
        ' "rationale": "indirect signal only"}'
    )
    f = SmallFilesCheck().run(_Q, _ctx(llm_response=high_conf))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_both_evidence_entries():
    f = SmallFilesCheck().run(_Q, _ctx(llm_response=_LLM_UNKNOWN))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = SmallFilesCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached even without LLM
