from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.customer_managed_keys import CustomerManagedKeysCheck

_Q = Question(
    id="STO-SCP-02",
    pillar_id="security-compliance-privacy",
    title="Use customer-managed keys where required",
    principle="Protect sensitive data at rest with customer-controlled encryption keys",
)

# Needles are distinct substrings of the two SQL strings:
#   "storage_credential_count" -> _STORAGE_CREDS_SQL (AS storage_credential_count)
#   "external_location_count"  -> _EXT_LOCATIONS_SQL  (AS external_location_count)
_FAKE_RESPONSES = {
    "storage_credential_count": [{"storage_credential_count": 4}],
    "external_location_count": [{"external_location_count": 8}],
}

_LLM_UNKNOWN = (
    '{"verdict": "unknown", "confidence": "low",'
    ' "score": null, "rationale": "CMK status is not observable from system tables."}'
)
_LLM_HIGH_CONF = (
    '{"verdict": "unknown", "confidence": "high",'
    ' "score": null, "rationale": "Cannot verify CMK from available evidence."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "medium",'
    ' "score": null, "rationale": "Some signals suggest maturity but CMK unconfirmed."}'
)


def _ctx(*, llm_response: str | None = _LLM_UNKNOWN) -> AgentContext:
    return AgentContext(
        assessment_id="a2",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_two_evidence_entries():
    ev = CustomerManagedKeysCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_proxy_evidence_kind_is_sql():
    ev = CustomerManagedKeysCheck().collect(_ctx())
    assert ev[0].kind == "sql"


def test_collect_proxy_evidence_summary_contains_credential_and_location_counts():
    ev = CustomerManagedKeysCheck().collect(_ctx())
    proxy_ev = ev[0]
    assert "4" in proxy_ev.summary  # storage_credential_count
    assert "8" in proxy_ev.summary  # external_location_count


def test_collect_proxy_evidence_states_cmk_not_observable():
    ev = CustomerManagedKeysCheck().collect(_ctx())
    assert "NOT observable" in ev[0].summary or "not observable" in ev[0].summary.lower()


def test_collect_note_kind_is_note():
    ev = CustomerManagedKeysCheck().collect(_ctx())
    assert ev[1].kind == "note"
    assert ev[1].rows == []


def test_collect_note_mentions_account_console():
    ev = CustomerManagedKeysCheck().collect(_ctx())
    assert "account console" in ev[1].summary or "account-level" in ev[1].summary


def test_collect_note_mentions_sa_confirmation():
    ev = CustomerManagedKeysCheck().collect(_ctx())
    assert "Admin confirmation" in ev[1].summary


def test_collect_empty_sql_results_handled():
    ctx = AgentContext(
        assessment_id="a2b",
        layer="storage",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = CustomerManagedKeysCheck().collect(ctx)
    assert "0" in ev[0].summary


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_unknown_verdict_with_low_confidence():
    f = CustomerManagedKeysCheck().run(_Q, _ctx(llm_response=_LLM_UNKNOWN))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
    assert f.sources


def test_judge_confidence_capped_at_medium_when_llm_claims_high():
    f = CustomerManagedKeysCheck().run(_Q, _ctx(llm_response=_LLM_HIGH_CONF))
    assert f.verdict is Verdict.UNKNOWN
    # claimed "high" must be capped to medium
    assert f.confidence is Confidence.MEDIUM


def test_judge_partial_verdict():
    f = CustomerManagedKeysCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = CustomerManagedKeysCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
