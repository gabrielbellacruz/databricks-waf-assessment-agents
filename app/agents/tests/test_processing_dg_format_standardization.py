from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.dg_format_standardization import (
    ProcessingFormatStandardizationCheck,
)

_Q = Question(
    id="PRO-DG-05",
    pillar_id="data-ai-governance",
    title="Standardize formats and definitions in transformations",
    principle="Use consistent shared definitions across transformation outputs",
)

# Distinct SQL needles:
#   "ORDER BY table_count DESC"  -> _RECURRING_COLUMNS_SQL (has ORDER BY + LIMIT 50)
#   "inconsistent_columns"       -> _INCONSISTENT_COLUMNS_SQL only
_FAKE_RESPONSES = {
    "ORDER BY table_count DESC": [
        {"column_name": "customer_id", "table_count": 12, "type_count": 2},
        {"column_name": "event_date", "table_count": 8, "type_count": 1},
    ],
    "inconsistent_columns": [{"inconsistent_columns": 5}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_recurring_columns_evidence():
    ev = ProcessingFormatStandardizationCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    # 2 recurring columns, 1 with mixed types
    assert "1" in ev[0].summary  # mixed_type_cols count
    assert "2" in ev[0].summary  # total recurring


def test_collect_inconsistent_columns_evidence():
    ev = ProcessingFormatStandardizationCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "5" in ev[1].summary  # inconsistent_count


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "customer_id has two data types across tables"}'
    )
    f = ProcessingFormatStandardizationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "Many shared column names have inconsistent types"}'
    )
    f = ProcessingFormatStandardizationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = ProcessingFormatStandardizationCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
