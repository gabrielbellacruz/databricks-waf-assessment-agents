from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.r_reproducibility import MlReproducibilityCheck

_Q = Question(
    id="ML-R-03",
    pillar_id="reliability",
    title="Ensure reproducible training runs",
    principle="Take a data-centric approach to machine learning",
)

_JOB_ROWS = [
    {"total_runs": 50, "distinct_jobs": 10, "failed_runs": 3, "avg_duration_s": 120.5}
]


def _ctx(*, job_rows=None, llm_response: str | None = "") -> AgentContext:
    rows = job_rows if job_rows is not None else _JOB_ROWS
    return AgentContext(
        assessment_id="test-ml-r03",
        layer="ml",
        sql=FakeSqlClient({"period_end_time": rows}),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_summarises_run_stats():
    ev = MlReproducibilityCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "50" in ev[0].summary
    assert "10 distinct jobs" in ev[0].summary


def test_collect_includes_failure_percentage():
    ev = MlReproducibilityCheck().collect(_ctx())
    # 3/50 = 6.0%
    assert "6.0%" in ev[0].summary


def test_collect_no_runs_returns_empty_summary():
    ev = MlReproducibilityCheck().collect(_ctx(job_rows=[]))
    assert "No completed job runs found" in ev[0].summary


def test_collect_attaches_limitation_note():
    ev = MlReproducibilityCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "MLflow" in ev[1].summary


def test_judge_unknown_verdict_when_evidence_weak():
    resp = (
        '{"verdict": "unknown", "confidence": "low", "score": null,'
        ' "rationale": "No direct reproducibility signal"}'
    )
    f = MlReproducibilityCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_no_llm_degrades_to_unassessed():
    f = MlReproducibilityCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
