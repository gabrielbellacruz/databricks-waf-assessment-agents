"""Tests for EncryptInTransitCheck (ING-SCP-03)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.encrypt_in_transit import EncryptInTransitCheck

_Q = Question(
    id="ING-SCP-03",
    pillar_id="security-compliance-privacy",
    title="Encrypt data in transit from source systems",
    principle="Protect data at rest and in transit",
)

# Three external locations: two TLS-backed, one insecure.
_ROWS = [{"total_locations": 3, "tls_scheme": 2, "insecure_scheme": 1}]


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient({"external_locations": _ROWS}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_produces_sql_and_note_evidence():
    ev = EncryptInTransitCheck().collect(_ctx())
    assert len(ev) == 2
    kinds = {e.kind for e in ev}
    assert "sql" in kinds
    assert "note" in kinds


def test_collect_sql_evidence_reflects_counts():
    ev = EncryptInTransitCheck().collect(_ctx())
    sql_ev = next(e for e in ev if e.kind == "sql")
    assert sql_ev.kind == "sql"
    # Summary must mention all three counts from the query result.
    assert "3" in sql_ev.summary   # total_locations
    assert "2" in sql_ev.summary   # tls_scheme
    assert "1" in sql_ev.summary   # insecure_scheme
    # Detail must contain the SQL so the source is traceable.
    assert "external_locations" in sql_ev.detail
    # Rows carry the raw counters for downstream rendering.
    row = sql_ev.rows[0]
    assert row["total_locations"] == 3
    assert row["tls_scheme"] == 2
    assert row["insecure_scheme"] == 1


def test_collect_note_evidence_present():
    ev = EncryptInTransitCheck().collect(_ctx())
    note_ev = next(e for e in ev if e.kind == "note")
    assert note_ev.rows == []
    assert note_ev.ref is not None
    assert "TLS" in note_ev.summary or "system tables" in note_ev.summary


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "2 of 3 locations use TLS-backed schemes; 1 insecure"}'
    )
    f = EncryptInTransitCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even when it claims high.
    assert f.confidence is Confidence.MEDIUM
    assert f.sources  # evidence attached for explainability


def test_no_llm_degrades_to_unassessed():
    f = EncryptInTransitCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached so a reviewer can inspect what was collected.
    assert f.sources
