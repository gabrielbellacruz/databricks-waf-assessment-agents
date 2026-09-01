"""Tests for ConnectionQuotasCheck (ING-OE-05)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.connection_quotas import ConnectionQuotasCheck

_Q = Question(
    id="ING-OE-05",
    pillar_id="operational-excellence",
    title="Manage source connection limits and API quotas",
    principle="Protect against cascading source-system failures",
)

# Canned system.query.history aggregate row: a few throttle mentions in 90 days.
_SQL_ROWS = [{"throttle_mentions": 3, "total_stmts": 1200}]

_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "medium", "score": null,'
    ' "rationale": "3 throttle mentions detected; config not verifiable."}'
)
_LLM_UNKNOWN = (
    '{"verdict": "unknown", "confidence": "low", "score": null,'
    ' "rationale": "No direct evidence of quota management configuration."}'
)


def _ctx(
    *, llm_response: str | None = _LLM_PARTIAL, rows: list[dict] | None = None
) -> AgentContext:
    sql_rows = _SQL_ROWS if rows is None else rows
    return AgentContext(
        assessment_id="test-assessment",
        layer="ingestion",
        sql=FakeSqlClient({"system.query.history": sql_rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_two_evidence_entries():
    ev = ConnectionQuotasCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_kind_and_content():
    ev = ConnectionQuotasCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert "mentions=3" in sql_ev.summary
    assert "total statements=1200" in sql_ev.summary
    assert sql_ev.rows == [{"throttle_mentions": 3, "total_stmts": 1200}]


def test_collect_note_evidence_kind_and_no_rows():
    ev = ConnectionQuotasCheck().collect(_ctx())
    note_ev = ev[1]
    assert note_ev.kind == "note"
    assert note_ev.rows == []
    assert note_ev.ref == "https://docs.databricks.com/en/ingestion/index.html"


def test_collect_note_summary_mentions_configuration_gap():
    ev = ConnectionQuotasCheck().collect(_ctx())
    note_summary = ev[1].summary.lower()
    assert (
        "connection" in note_summary
        or "quota" in note_summary
        or "sa confirmation" in note_summary
    )


def test_collect_no_rows_reports_zero():
    ev = ConnectionQuotasCheck().collect(_ctx(rows=[]))
    sql_ev = ev[0]
    assert sql_ev.rows == [{"throttle_mentions": 0, "total_stmts": 0}]
    assert "mentions=0" in sql_ev.summary


def test_collect_zero_row_result_is_handled():
    """FakeSqlClient returns [] when no needle matches; must not raise."""
    ctx = AgentContext(
        assessment_id="t2",
        layer="ingestion",
        sql=FakeSqlClient({}),  # no key matches -> returns []
        catalogs=[],
        llm=None,
    )
    ev = ConnectionQuotasCheck().collect(ctx)
    assert ev[0].rows == [{"throttle_mentions": 0, "total_stmts": 0}]


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_partial_verdict_mapped():
    f = ConnectionQuotasCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources  # evidence attached


def test_judge_unknown_verdict_mapped():
    f = ConnectionQuotasCheck().run(_Q, _ctx(llm_response=_LLM_UNKNOWN))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_judge_confidence_capped_at_medium_when_llm_claims_high():
    high_conf = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "quota management in place"}'
    )
    f = ConnectionQuotasCheck().run(_Q, _ctx(llm_response=high_conf))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_both_evidence_entries():
    f = ConnectionQuotasCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = ConnectionQuotasCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached even without LLM
