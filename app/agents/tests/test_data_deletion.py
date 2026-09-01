from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.data_deletion import DataDeletionCheck

_Q = Question(
    id="STO-SCP-05",
    pillar_id="security-compliance-privacy",
    title="Support data deletion and privacy requests on stored data",
    principle="Ensure stored data can be deleted to meet privacy obligations",
)

# Needles are distinct substrings of the two SQL strings:
#   "DELETE FROM"        -> _DELETE_HISTORY_SQL  (ILIKE '%DELETE FROM%')
#   "delta_format_count" -> _DELTA_FORMAT_SQL     (AS delta_format_count alias)
_FAKE_RESPONSES = {
    "DELETE FROM": [{"delete_stmts": 15, "total_stmts": 500}],
    "delta_format_count": [{"total_tables": 60, "delta_format_count": 54}],
}

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium",'
    ' "score": null, "rationale": "Active DELETE usage and high Delta share indicate strong '
    'deletion capability."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "high",'
    ' "score": null, "rationale": "Some DELETE activity but GDPR process not confirmed."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "medium",'
    ' "score": null, "rationale": "No DELETE statements and mostly non-Delta tables."}'
)


def _ctx(*, llm_response: str | None = _LLM_MET) -> AgentContext:
    return AgentContext(
        assessment_id="a4",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_three_evidence_entries():
    ev = DataDeletionCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_delete_history_evidence_kind_is_sql():
    ev = DataDeletionCheck().collect(_ctx())
    assert ev[0].kind == "sql"


def test_collect_delete_history_summary_contains_counts():
    ev = DataDeletionCheck().collect(_ctx())
    summary = ev[0].summary
    assert "15" in summary   # delete_stmts
    assert "500" in summary  # total_stmts


def test_collect_delete_history_rows():
    ev = DataDeletionCheck().collect(_ctx())
    assert ev[0].rows == [{"delete_stmts": 15, "total_stmts": 500}]


def test_collect_delta_format_evidence_summary_contains_counts():
    ev = DataDeletionCheck().collect(_ctx())
    summary = ev[1].summary
    assert "54" in summary  # delta_format_count
    assert "60" in summary  # total_tables


def test_collect_delta_format_evidence_contains_percentage():
    ev = DataDeletionCheck().collect(_ctx())
    # 54 / 60 = 90.0%
    assert "90.0%" in ev[1].summary


def test_collect_note_kind_is_note():
    ev = DataDeletionCheck().collect(_ctx())
    assert ev[2].kind == "note"
    assert ev[2].rows == []


def test_collect_note_mentions_gdpr_not_observable():
    ev = DataDeletionCheck().collect(_ctx())
    note_summary = ev[2].summary
    assert "GDPR" in note_summary or "erasure" in note_summary.lower()
    assert "NOT observable" in note_summary or "not observable" in note_summary.lower()


def test_collect_empty_query_history_returns_fallback_evidence():
    ctx = AgentContext(
        assessment_id="a4b",
        layer="storage",
        sql=FakeSqlClient({"delta_format_count": [{"total_tables": 20, "delta_format_count": 10}]}),
        catalogs=[],
        llm=None,
    )
    ev = DataDeletionCheck().collect(ctx)
    # No query.history match -> fallback "no rows" evidence
    assert ev[0].rows == []
    assert "No query-history rows" in ev[0].summary


def test_collect_empty_sql_client_handled():
    ctx = AgentContext(
        assessment_id="a4c",
        layer="storage",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = DataDeletionCheck().collect(ctx)
    assert len(ev) == 3


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_met_verdict():
    f = DataDeletionCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_partial_verdict_and_caps_high_confidence_to_medium():
    f = DataDeletionCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL
    # LLM claimed "high" — must be capped to medium
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    f = DataDeletionCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET


def test_judge_sources_include_all_evidence_kinds():
    f = DataDeletionCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = {e.kind for e in f.sources}
    assert "sql" in kinds
    assert "note" in kinds


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = DataDeletionCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
