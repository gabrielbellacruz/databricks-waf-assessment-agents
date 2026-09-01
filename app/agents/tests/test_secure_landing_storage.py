"""Tests for SecureLandingStorageCheck (ING-SCP-02)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.secure_landing_storage import SecureLandingStorageCheck

_Q = Question(
    id="ING-SCP-02",
    pillar_id="security-compliance-privacy",
    title="Secure access to landing cloud storage",
    principle="Protect data in transit and at rest",
)

# Four governed external locations, all TLS-backed, three with named credentials.
_EXT_LOC_ROWS = [{"total_locations": 4, "tls_backed": 4, "credential_backed": 3}]


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient({"external_locations": _EXT_LOC_ROWS}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_evidence_reflects_counts():
    ev = SecureLandingStorageCheck().collect(_ctx())
    assert len(ev) == 1
    e = ev[0]
    assert e.kind == "sql"
    # Summary mentions the total count
    assert "4" in e.summary
    # Detail contains the SQL used (which references external_locations)
    assert "external_locations" in e.detail
    # Rows carry all three counters
    row = e.rows[0]
    assert row["total_locations"] == 4
    assert row["tls_backed"] == 4
    assert row["credential_backed"] == 3


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "4 UC external locations, all TLS-backed, 3 with named credentials"}'
    )
    f = SecureLandingStorageCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    # LLM confidence is capped at medium even when it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources  # evidence attached for explainability


def test_no_llm_degrades_to_unassessed():
    f = SecureLandingStorageCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached despite no LLM
