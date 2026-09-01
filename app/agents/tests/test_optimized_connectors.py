from __future__ import annotations

from waf_agents.core.clients import (
    AgentContext,
    FakeLlmClient,
    FakeSqlClient,
)
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.optimized_connectors import OptimizedConnectorsCheck

_Q = Question(
    id="ING-IU-01",
    pillar_id="interoperability-usability",
    title="Use optimized connectors to ingest data sources",
    principle="Use native and managed ingestion paths",
)

_LINEAGE_ROWS = [
    {"source_type": "DELTA", "n": 120},
    {"source_type": "PARQUET", "n": 45},
    {"source_type": "JDBC", "n": 8},
]
_PIPELINE_ROWS = [{"n": 5}]


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    sql = FakeSqlClient(
        {
            "table_lineage": _LINEAGE_ROWS,
            "system.lakeflow.pipelines": _PIPELINE_ROWS,
        }
    )
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=sql,
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_reflects_source_type_rows():
    ev = OptimizedConnectorsCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    # source_type breakdown rows are surfaced in the first evidence entry
    assert any(r["source_type"] == "DELTA" for r in ev[0].rows)
    assert "table_lineage" in ev[0].detail


def test_collect_pipeline_count_in_second_evidence():
    ev = OptimizedConnectorsCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "5" in ev[1].summary


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "some managed pipelines but bespoke JDBC paths also present"}'
    )
    f = OptimizedConnectorsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even when it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources  # evidence attached for explainability


def test_no_llm_degrades_to_unassessed():
    f = OptimizedConnectorsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached


def test_collect_empty_sql_is_graceful():
    sql = FakeSqlClient()  # no canned rows -> returns [] for every query
    ctx = AgentContext(
        assessment_id="a2",
        layer="ingestion",
        sql=sql,
        llm=None,
    )
    ev = OptimizedConnectorsCheck().collect(ctx)
    assert ev[0].rows == []
    assert "no lineage data" in ev[0].summary
    assert ev[1].rows == []
