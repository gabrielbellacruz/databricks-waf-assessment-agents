from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.pe_bottleneck_identification import BottleneckIdentificationCheck

_Q = Question(
    id="PRO-PE-04",
    pillar_id="performance-efficiency",
    title="Identify bottlenecks in transformation chains",
    principle="Continuously optimise processing performance",
)

# needle "max_run_seconds" -> pe_bottleneck_identification SQL (unique to that module)
_SQL_ROWS = [
    {
        "total_runs": 50,
        "failed_runs": 5,
        "avg_run_seconds": 1800.0,
        "max_run_seconds": 7200.0,
    }
]

_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "medium", "score": null,'
    ' "rationale": "Long average duration and failures suggest unresolved bottlenecks."}'
)
_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "Run durations and failure rate are within acceptable range."}'
)


def _ctx(*, llm_response: str | None = _LLM_MET, rows: list[dict] | None = None) -> AgentContext:
    sql_rows = _SQL_ROWS if rows is None else rows
    return AgentContext(
        assessment_id="test-assessment",
        layer="processing",
        sql=FakeSqlClient({"max_run_seconds": sql_rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_two_evidence_entries():
    ev = BottleneckIdentificationCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_counts():
    ev = BottleneckIdentificationCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert sql_ev.rows[0]["total_runs"] == 50
    assert sql_ev.rows[0]["failed_runs"] == 5
    assert sql_ev.rows[0]["avg_run_seconds"] == 1800.0


def test_collect_summary_mentions_failure_pct():
    ev = BottleneckIdentificationCheck().collect(_ctx())
    assert "10.0%" in ev[0].summary


def test_collect_note_mentions_spark_ui():
    ev = BottleneckIdentificationCheck().collect(_ctx())
    note_ev = ev[1]
    assert note_ev.kind == "note"
    assert "Spark UI" in note_ev.summary


def test_collect_no_runs():
    ctx = AgentContext(
        assessment_id="t2",
        layer="processing",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = BottleneckIdentificationCheck().collect(ctx)
    assert "No job runs found" in ev[0].summary
    assert ev[0].rows[0]["total_runs"] == 0


def test_judge_met_verdict():
    f = BottleneckIdentificationCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_partial_verdict():
    f = BottleneckIdentificationCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL


def test_judge_confidence_capped_at_medium():
    high_conf = (
        '{"verdict": "not_met", "confidence": "high", "score": null,'
        ' "rationale": "long runs indicate bottlenecks"}'
    )
    f = BottleneckIdentificationCheck().run(_Q, _ctx(llm_response=high_conf))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = BottleneckIdentificationCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
