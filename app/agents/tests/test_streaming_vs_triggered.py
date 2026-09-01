from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.streaming_vs_triggered import StreamingVsTriggeredCheck

_Q = Question(
    id="ING-CO-02",
    pillar_id="cost-optimization",
    title="Balance always-on streaming against triggered ingestion",
    principle="Optimize cost by matching job triggers to latency requirements",
)

# FakeSqlClient keyed on a substring present in the query.
_SQL_ROWS = [{"total_jobs": 10, "continuous_jobs": 8, "triggered_jobs": 2}]


def _ctx(*, llm_response: str | None = "", sql_rows: list[dict] | None = None) -> AgentContext:
    rows = sql_rows if sql_rows is not None else _SQL_ROWS
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient({"system.lakeflow.jobs": rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_sql_evidence_with_counts():
    ev = StreamingVsTriggeredCheck().collect(_ctx())
    assert len(ev) == 1
    e = ev[0]
    assert e.kind == "sql"
    # Summary must mention both continuous and total counts.
    assert "8" in e.summary
    assert "10" in e.summary
    assert e.rows == [{"total_jobs": 10, "continuous_jobs": 8, "triggered_jobs": 2}]
    assert e.ref is not None
    assert "system.lakeflow.jobs" in e.detail


def test_collect_handles_empty_rows():
    ev = StreamingVsTriggeredCheck().collect(_ctx(sql_rows=[]))
    assert len(ev) == 1
    e = ev[0]
    assert e.kind == "sql"
    assert "No rows" in e.summary
    assert e.rows == []


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "not_met", "confidence": "high", '
        '"score": null, "rationale": "8 of 10 jobs are continuous"}'
    )
    f = StreamingVsTriggeredCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    # LLM confidence is capped at medium even when model claims high.
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_no_llm_degrades_to_unassessed():
    f = StreamingVsTriggeredCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability.
    assert f.sources
