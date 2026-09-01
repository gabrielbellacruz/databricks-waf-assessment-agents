from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.scp_sensitive_training_data import SensitiveTrainingDataCheck

_Q = Question(
    id="ML-SCP-02",
    pillar_id="security-compliance-privacy",
    title="Protect sensitive training data",
    principle="Apply data protection controls to ML training data",
)

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "Row filters and column masks applied across multiple catalogs."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "medium", "score": null,'
    ' "rationale": "No row filters or column masks found."}'
)


def _ctx(
    *,
    llm_response: str | None = _LLM_MET,
    filter_rows: list[dict] | None = None,
    mask_rows: list[dict] | None = None,
    access_rows: list[dict] | None = None,
) -> AgentContext:
    sql_resp: dict[str, list[dict]] = {}
    # Needle for _ROW_FILTERS_SQL — "tables_with_row_filter" column
    sql_resp["tables_with_row_filter"] = filter_rows if filter_rows is not None else [
        {"tables_with_row_filter": 4, "catalogs_covered": 2}
    ]
    # Needle for _COL_MASKS_SQL — "columns_with_mask" column
    sql_resp["columns_with_mask"] = mask_rows if mask_rows is not None else [
        {"columns_with_mask": 12, "catalogs_covered": 2}
    ]
    # Needle for _DATA_ACCESS_SQL — "distinct_readers" column
    sql_resp["distinct_readers"] = access_rows if access_rows is not None else [
        {"distinct_readers": 5, "sp_reads": 30}
    ]
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(sql_resp),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_four_entries():
    ev = SensitiveTrainingDataCheck().collect(_ctx())
    assert len(ev) == 4


def test_collect_row_filter_evidence():
    ev = SensitiveTrainingDataCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "4" in ev[0].summary
    assert ev[0].rows[0]["tables_with_row_filter"] == 4


def test_collect_mask_evidence():
    ev = SensitiveTrainingDataCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "12" in ev[1].summary
    assert ev[1].rows[0]["columns_with_mask"] == 12


def test_collect_access_evidence_shows_sp_reads():
    ev = SensitiveTrainingDataCheck().collect(_ctx())
    assert ev[2].kind == "sql"
    assert "5" in ev[2].summary
    assert "30" in ev[2].summary
    assert ev[2].rows[0]["sp_reads"] == 30


def test_collect_note_evidence_present():
    ev = SensitiveTrainingDataCheck().collect(_ctx())
    note = ev[3]
    assert note.kind == "note"
    assert note.rows == []


def test_collect_empty_sql_safe():
    ctx = AgentContext(
        assessment_id="t2",
        layer="ml",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = SensitiveTrainingDataCheck().collect(ctx)
    # Should not raise; all counts default to 0
    assert ev[0].rows[0]["tables_with_row_filter"] == 0
    assert ev[1].rows[0]["columns_with_mask"] == 0


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_met_verdict():
    f = SensitiveTrainingDataCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    f = SensitiveTrainingDataCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET


def test_judge_confidence_capped_at_medium():
    resp = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "Strong controls."}'
    )
    f = SensitiveTrainingDataCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_attached():
    f = SensitiveTrainingDataCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.sources


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = SensitiveTrainingDataCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
