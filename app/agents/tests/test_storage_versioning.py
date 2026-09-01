from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.storage_versioning import StorageVersioningCheck

_Q = Question(
    id="STO-SCP-04",
    pillar_id="security-compliance-privacy",
    title="Enable storage versioning for recovery",
    principle="Ensure data can be recovered to a prior point in time",
)

# Needle is a distinct substring of _DELTA_TABLE_SQL:
#   "delta_table_count" -> AS delta_table_count alias (unique to this check)
_FAKE_RESPONSES = {
    "delta_table_count": [{"total_tables": 80, "delta_table_count": 72}],
}

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium",'
    ' "score": null, "rationale": "90% of tables are Delta — strong versioning posture."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "high",'
    ' "score": null, "rationale": "Majority of tables are Delta but bucket versioning unknown."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "medium",'
    ' "score": null, "rationale": "Few Delta tables; versioning capability is weak."}'
)


def _ctx(*, llm_response: str | None = _LLM_MET, rows: list[dict] | None = None) -> AgentContext:
    responses = (
        {"delta_table_count": rows}
        if rows is not None
        else dict(_FAKE_RESPONSES)
    )
    return AgentContext(
        assessment_id="a3",
        layer="storage",
        sql=FakeSqlClient(responses),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_two_evidence_entries():
    ev = StorageVersioningCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_delta_evidence_kind_is_sql():
    ev = StorageVersioningCheck().collect(_ctx())
    assert ev[0].kind == "sql"


def test_collect_delta_evidence_summary_contains_counts():
    ev = StorageVersioningCheck().collect(_ctx())
    summary = ev[0].summary
    assert "72" in summary   # delta_table_count
    assert "80" in summary   # total_tables


def test_collect_delta_evidence_summary_contains_percentage():
    ev = StorageVersioningCheck().collect(_ctx())
    # 72 / 80 = 90.0 %
    assert "90.0%" in ev[0].summary


def test_collect_delta_evidence_rows():
    ev = StorageVersioningCheck().collect(_ctx())
    assert ev[0].rows == [{"total_tables": 80, "delta_table_count": 72}]


def test_collect_note_kind_is_note():
    ev = StorageVersioningCheck().collect(_ctx())
    assert ev[1].kind == "note"
    assert ev[1].rows == []


def test_collect_note_mentions_bucket_versioning_not_visible():
    ev = StorageVersioningCheck().collect(_ctx())
    note_summary = ev[1].summary
    assert "bucket" in note_summary.lower() or "object versioning" in note_summary.lower()
    assert "NOT visible" in note_summary or "not visible" in note_summary.lower()


def test_collect_zero_tables_shows_zero_percent():
    ev = StorageVersioningCheck().collect(_ctx(rows=[{"total_tables": 0, "delta_table_count": 0}]))
    assert "0 of 0" in ev[0].summary
    assert "0.0%" in ev[0].summary


def test_collect_empty_sql_response_handled():
    ctx = AgentContext(
        assessment_id="a3b",
        layer="storage",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = StorageVersioningCheck().collect(ctx)
    assert ev[0].rows == [{"total_tables": 0, "delta_table_count": 0}]


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_met_verdict():
    f = StorageVersioningCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_partial_verdict_and_caps_high_confidence_to_medium():
    f = StorageVersioningCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL
    # LLM claimed "high" — must be capped to medium
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    f = StorageVersioningCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = StorageVersioningCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
