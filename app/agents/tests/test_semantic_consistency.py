from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.semantic_consistency import SemanticConsistencyCheck

_Q = Question(
    id="STO-IU-05",
    pillar_id="interoperability-usability",
    title="Keep stored data semantically consistent across domains",
    principle="Shared data dimensions should have consistent definitions across domain boundaries",
)

_RECURRING_ROWS = [
    {"column_name": "customer_id", "table_count": 42, "type_count": 2},
    {"column_name": "event_date", "table_count": 30, "type_count": 1},
    {"column_name": "product_id", "table_count": 18, "type_count": 1},
]

# Needles are distinct AS aliases that don't appear in each other's SQL:
#   "table_count"           -> _RECURRING_COLUMNS_SQL  (AS table_count)
#   "inconsistent_columns"  -> _INCONSISTENT_COLUMNS_SQL  (AS inconsistent_columns)
_FAKE_RESPONSES = {
    "table_count": _RECURRING_ROWS,
    "inconsistent_columns": [{"inconsistent_columns": 5}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_recurring_columns_count():
    ev = SemanticConsistencyCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "3 column name" in ev[0].summary


def test_collect_mixed_type_count():
    ev = SemanticConsistencyCheck().collect(_ctx())
    # customer_id has type_count == 2 -> 1 mixed-type column among the recurring set
    assert "1 of those have inconsistent" in ev[0].summary


def test_collect_inconsistent_columns_evidence():
    ev = SemanticConsistencyCheck().collect(_ctx())
    assert len(ev) == 2
    assert "5 column name" in ev[1].summary


def test_collect_rows_attached():
    ev = SemanticConsistencyCheck().collect(_ctx())
    assert any(r.get("column_name") == "customer_id" for r in ev[0].rows)
    assert any(r.get("inconsistent_columns") == 5 for r in ev[1].rows)


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "Many shared columns have inconsistent data types"}'
    )
    f = SemanticConsistencyCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some type inconsistency detected"}'
    )
    f = SemanticConsistencyCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = SemanticConsistencyCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
