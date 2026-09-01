from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.network_controls import NetworkControlsCheck

_Q = Question(
    id="ING-SCP-05",
    pillar_id="security-compliance-privacy",
    title="Apply network controls to ingestion connectivity",
    principle="Secure the network perimeter of your ingestion layer",
)

# Canned SQL rows: 5 external locations registered.
_SQL_ROWS = [{"external_locations": 5}]

_LLM_UNKNOWN = (
    '{"verdict": "unknown", "confidence": "low", "score": null,'
    ' "rationale": "Network controls are not observable from system tables."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "medium", "score": null,'
    ' "rationale": "Some external locations exist but NCC status is unknown."}'
)


def _ctx(
    *, llm_response: str | None = _LLM_UNKNOWN, rows: list[dict] | None = None
) -> AgentContext:
    sql_rows = _SQL_ROWS if rows is None else rows
    return AgentContext(
        assessment_id="test-assessment",
        layer="ingestion",
        sql=FakeSqlClient({"external_locations": sql_rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_two_evidence_entries():
    ev = NetworkControlsCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_kind_and_content():
    ev = NetworkControlsCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert "5" in sql_ev.summary
    assert "external_locations" in sql_ev.summary.lower()
    assert sql_ev.rows == [{"external_locations": 5}]


def test_collect_note_evidence_is_dominant():
    """The note evidence is the second entry and carries the key explanatory text."""
    ev = NetworkControlsCheck().collect(_ctx())
    note_ev = ev[1]
    assert note_ev.kind == "note"
    assert note_ev.rows == []
    assert "NCC" in note_ev.summary
    assert "PrivateLink" in note_ev.summary
    assert note_ev.ref == "https://docs.databricks.com/en/security/network/index.html"


def test_collect_note_mentions_sa_confirmation():
    ev = NetworkControlsCheck().collect(_ctx())
    assert "admin confirmation" in ev[1].summary


def test_collect_no_sql_result_reports_zero():
    ev = NetworkControlsCheck().collect(_ctx(rows=[]))
    assert ev[0].rows == [{"external_locations": 0}]
    assert "0 external location" in ev[0].summary


def test_collect_empty_sql_client_handled():
    """FakeSqlClient returns [] when no needle matches; must not raise."""
    ctx = AgentContext(
        assessment_id="t2",
        layer="ingestion",
        sql=FakeSqlClient({}),  # no key matches -> returns []
        catalogs=[],
        llm=None,
    )
    ev = NetworkControlsCheck().collect(ctx)
    assert ev[0].rows == [{"external_locations": 0}]


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_unknown_verdict_mapped():
    f = NetworkControlsCheck().run(_Q, _ctx(llm_response=_LLM_UNKNOWN))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
    assert f.sources  # evidence attached


def test_judge_partial_verdict_mapped():
    f = NetworkControlsCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_confidence_capped_at_medium_when_llm_claims_high():
    high_conf = (
        '{"verdict": "unknown", "confidence": "high", "score": null,'
        ' "rationale": "Cannot determine from system tables."}'
    )
    f = NetworkControlsCheck().run(_Q, _ctx(llm_response=high_conf))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_both_evidence_entries():
    f = NetworkControlsCheck().run(_Q, _ctx(llm_response=_LLM_UNKNOWN))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = NetworkControlsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached even without LLM
