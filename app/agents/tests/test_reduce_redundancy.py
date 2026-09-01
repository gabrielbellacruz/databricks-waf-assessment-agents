from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.reduce_redundancy import ReduceRedundancyCheck

_Q = Question(
    id="STO-R-05",
    pillar_id="reliability",
    title="Reduce redundancy in stored data",
    principle="Manage storage efficiently and avoid unnecessary data copies",
)

# Needles are distinct, non-overlapping substrings of the three SQL queries:
#   "schema_count"  -> _DUPLICATE_NAMES_SQL (column alias unique to that query)
#   "view_count"    -> _VIEW_RATIO_SQL       (column alias unique to that query)
#   "ctas_stmts"    -> _CTAS_SQL             (column alias unique to that query)
_FAKE_RESPONSES = {
    "schema_count": [
        {"table_name": "orders", "schema_count": 5},
        {"table_name": "customers", "schema_count": 3},
    ],
    "view_count": [{"view_count": 30, "base_table_count": 120}],
    "ctas_stmts": [{"ctas_stmts": 14}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_duplicate_names_evidence():
    ev = ReduceRedundancyCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "2 table names" in ev[0].summary
    assert "orders" in ev[0].summary
    assert "5 schemas" in ev[0].summary


def test_collect_duplicate_names_rows():
    ev = ReduceRedundancyCheck().collect(_ctx())
    assert ev[0].rows[0]["table_name"] == "orders"
    assert ev[0].rows[0]["schema_count"] == 5


def test_collect_view_ratio_evidence():
    ev = ReduceRedundancyCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "30 views" in ev[1].summary
    assert "120 base tables" in ev[1].summary
    # 30 / (30 + 120) = 20.0%
    assert "20.0%" in ev[1].summary


def test_collect_view_ratio_rows():
    ev = ReduceRedundancyCheck().collect(_ctx())
    assert ev[1].rows[0]["view_count"] == 30
    assert ev[1].rows[0]["base_table_count"] == 120


def test_collect_ctas_evidence():
    ev = ReduceRedundancyCheck().collect(_ctx())
    assert ev[2].kind == "sql"
    assert "14 CREATE TABLE AS SELECT" in ev[2].summary


def test_collect_returns_three_evidence_items():
    ev = ReduceRedundancyCheck().collect(_ctx())
    assert len(ev) == 3


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "not_met", "confidence": "high",'
        ' "score": null, "rationale": "Many duplicate names and high CTAS rate"}'
    )
    f = ReduceRedundancyCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Some duplication present but views partially mitigate it"}'
    )
    f = ReduceRedundancyCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = ReduceRedundancyCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
