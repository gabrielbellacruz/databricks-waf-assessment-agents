from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.data_clustering import DataClusteringCheck

_Q = Question(
    id="STO-PE-01",
    pillar_id="performance-efficiency",
    title="Cluster stored data for common query patterns",
    principle="Optimize data layout for query access patterns",
)

# Needle: "CLUSTER BY" appears in the ILIKE clause of _SQL and nowhere else in
# the FakeSqlClient responses.
_FAKE_RESPONSES = {
    "CLUSTER BY": [
        {
            "liquid_cluster_stmts": 12,
            "zorder_stmts": 5,
            "partition_stmts": 8,
            "total_stmts": 1200,
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
    ev = DataClusteringCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    assert ev[1].kind == "note"


def test_collect_sql_summary_contains_counts():
    ev = DataClusteringCheck().collect(_ctx())
    assert "CLUSTER BY=12" in ev[0].summary
    assert "ZORDER BY=5" in ev[0].summary


def test_collect_sql_evidence_has_rows():
    ev = DataClusteringCheck().collect(_ctx())
    assert ev[0].rows[0]["liquid_cluster_stmts"] == 12
    assert ev[0].rows[0]["zorder_stmts"] == 5
    assert ev[0].rows[0]["partition_stmts"] == 8


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some liquid clustering observed"}'
    )
    f = DataClusteringCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Consistent liquid clustering usage seen"}'
    )
    f = DataClusteringCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = DataClusteringCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
