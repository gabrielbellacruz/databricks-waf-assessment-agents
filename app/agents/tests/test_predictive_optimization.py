from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.predictive_optimization import PredictiveOptimizationCheck

_Q = Question(
    id="STO-PE-04",
    pillar_id="performance-efficiency",
    title="Enable Predictive Optimization for stored tables",
    principle="Let Databricks manage Delta table maintenance automatically",
)

# Two distinct needles, one per SQL:
#   "optimize_stmts"    -> _SQL_MAINTENANCE  (AS optimize_stmts alias)
#   "data_source_format" -> _SQL_DELTA       (data_source_format column)
_FAKE_RESPONSES = {
    "optimize_stmts": [
        {"optimize_stmts": 3, "vacuum_stmts": 1, "total_stmts": 500}
    ],
    "data_source_format": [
        {"total_tables": 100, "delta_tables": 92}
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidences():
    ev = PredictiveOptimizationCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[0].kind == "sql"   # maintenance commands
    assert ev[1].kind == "sql"   # delta table share
    assert ev[2].kind == "note"  # observability gap


def test_collect_maint_summary_contains_counts():
    ev = PredictiveOptimizationCheck().collect(_ctx())
    assert "OPTIMIZE=3" in ev[0].summary
    assert "VACUUM=1" in ev[0].summary


def test_collect_delta_summary_contains_percentage():
    ev = PredictiveOptimizationCheck().collect(_ctx())
    # 92 / 100 = 92.0%
    assert "92.0%" in ev[1].summary


def test_collect_delta_evidence_has_rows():
    ev = PredictiveOptimizationCheck().collect(_ctx())
    assert ev[1].rows[0]["delta_tables"] == 92
    assert ev[1].rows[0]["total_tables"] == 100


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "unknown", "confidence": "high",'
        ' "score": null, "rationale": "PO enablement not directly observable"}'
    )
    f = PredictiveOptimizationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "low",'
        ' "score": null, "rationale": "Low manual maintenance suggests PO may be active"}'
    )
    f = PredictiveOptimizationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.LOW


def test_no_llm_degrades_to_unassessed():
    f = PredictiveOptimizationCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
