from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.data_skipping import DataSkippingCheck

_Q = Question(
    id="STO-PE-03",
    pillar_id="performance-efficiency",
    title="Enable data skipping and statistics on stored tables",
    principle="Maximise query-time data skipping via fresh statistics",
)

# Needle: "COMPUTE STATISTICS" appears in the ILIKE clause of DataSkippingCheck._SQL.
_FAKE_RESPONSES = {
    "COMPUTE STATISTICS": [
        {
            "analyze_stmts": 6,
            "analyze_table_stmts": 6,
            "layout_stmts": 9,
            "total_stmts": 800,
        }
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


def test_collect_returns_two_evidences():
    ev = DataSkippingCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    assert ev[1].kind == "note"


def test_collect_sql_summary_contains_analyze_count():
    ev = DataSkippingCheck().collect(_ctx())
    assert "COMPUTE STATISTICS=6" in ev[0].summary


def test_collect_sql_summary_contains_layout_count():
    ev = DataSkippingCheck().collect(_ctx())
    assert "layout (ZORDER/CLUSTER BY)=9" in ev[0].summary


def test_collect_sql_evidence_has_rows():
    ev = DataSkippingCheck().collect(_ctx())
    assert ev[0].rows[0]["analyze_stmts"] == 6
    assert ev[0].rows[0]["layout_stmts"] == 9
    assert ev[0].rows[0]["total_stmts"] == 800


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "ANALYZE TABLE present but infrequent"}'
    )
    f = DataSkippingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Regular statistics refresh observed"}'
    )
    f = DataSkippingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = DataSkippingCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
