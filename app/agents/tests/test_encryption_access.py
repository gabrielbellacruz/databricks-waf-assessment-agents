from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.encryption_access import EncryptionAccessCheck

_Q = Question(
    id="STO-SCP-01",
    pillar_id="security-compliance-privacy",
    title="Encrypt stored data and restrict access",
    principle="Protect data at rest and govern who can reach it",
)

# Needles are distinct substrings of the four SQL strings:
#   "external_location_count" -> _EXT_LOCATIONS_SQL (AS external_location_count)
#   "storage_credential_count" -> _STORAGE_CREDS_SQL (AS storage_credential_count)
#   "external_tables"          -> _TABLE_TYPE_SQL (AS external_tables)
#   "broad_grants"             -> _GRANT_BREADTH_SQL (AS broad_grants)
_FAKE_RESPONSES = {
    "external_location_count": [{"external_location_count": 6}],
    "storage_credential_count": [{"storage_credential_count": 3}],
    "external_tables": [{"total_tables": 100, "external_tables": 40}],
    "broad_grants": [{"total_grants": 200, "broad_grants": 10}],
}

_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "high",'
    ' "score": null, "rationale": "Most tables use governed paths but some grants are broad."}'
)
_LLM_MET = (
    '{"verdict": "met", "confidence": "medium",'
    ' "score": null, "rationale": "Storage is well governed with narrow grants."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "medium",'
    ' "score": null, "rationale": "Wide-open grants and no governed external locations."}'
)


def _ctx(*, llm_response: str | None = _LLM_PARTIAL) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_three_evidence_entries():
    ev = EncryptionAccessCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_gov_evidence_summary_contains_location_and_credential_counts():
    ev = EncryptionAccessCheck().collect(_ctx())
    gov_ev = ev[0]
    assert gov_ev.kind == "sql"
    assert "6" in gov_ev.summary  # external_location_count
    assert "3" in gov_ev.summary  # storage_credential_count


def test_collect_gov_evidence_summary_contains_table_stats():
    ev = EncryptionAccessCheck().collect(_ctx())
    gov_ev = ev[0]
    assert "40" in gov_ev.summary   # external_tables
    assert "100" in gov_ev.summary  # total_tables


def test_collect_grant_evidence_summary_contains_grant_counts():
    ev = EncryptionAccessCheck().collect(_ctx())
    grant_ev = ev[1]
    assert grant_ev.kind == "sql"
    assert "200" in grant_ev.summary  # total_grants
    assert "10" in grant_ev.summary   # broad_grants


def test_collect_note_evidence_mentions_encryption_not_visible():
    ev = EncryptionAccessCheck().collect(_ctx())
    note_ev = ev[2]
    assert note_ev.kind == "note"
    assert note_ev.rows == []
    assert "NOT visible" in note_ev.summary or "not visible" in note_ev.summary.lower()


def test_collect_note_evidence_references_sa_confirmation():
    ev = EncryptionAccessCheck().collect(_ctx())
    assert "Admin confirmation" in ev[2].summary


def test_collect_gov_evidence_has_rows():
    ev = EncryptionAccessCheck().collect(_ctx())
    assert ev[0].rows  # combined rows from ext + cred + table queries


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_maps_partial_verdict_and_caps_high_confidence_to_medium():
    f = EncryptionAccessCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL
    # LLM claimed "high" — must be capped to medium
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_met_verdict():
    f = EncryptionAccessCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    f = EncryptionAccessCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET


def test_judge_sources_include_all_evidence_kinds():
    f = EncryptionAccessCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    kinds = {e.kind for e in f.sources}
    assert "sql" in kinds
    assert "note" in kinds


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = EncryptionAccessCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence still attached for explainability
    assert f.sources
