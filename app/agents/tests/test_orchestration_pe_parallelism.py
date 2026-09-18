from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.pe_parallelism import OrcParallelismCheck

_Q = Question(
    id="ORC-PE-01",
    pillar_id="performance-efficiency",
    title="Parallelize independent workflow tasks",
    principle="Optimize performance through efficient task design",
)

# Distinct needles:
#   "job_task_run_timeline" → _SQL_TASKS (task-grain table; not in _SQL_DURATION)
#   "avg_run_seconds"       → _SQL_DURATION (but also in pe_prewarming — OK, different module)
_FAKE = {
    "job_task_run_timeline": [{"total_jobs": 20, "multi_task_jobs": 14}],
    "avg_run_seconds": [{"total_runs": 80, "avg_run_seconds": 350.5}],
}

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "14 of 20 jobs are multi-task; likely parallel execution."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "low", "score": null,'
    ' "rationale": "Some multi-task jobs exist but parallelism unconfirmed."}'
)


def _ctx(
    *,
    llm_response: str | None = _LLM_MET,
    fake: dict | None = None,
) -> AgentContext:
    return AgentContext(
        assessment_id="test-orc",
        layer="orchestration",
        sql=FakeSqlClient(fake if fake is not None else dict(_FAKE)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# --- collect() ---

def test_collect_returns_three_evidence_entries():
    ev = OrcParallelismCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_tasks_evidence_content():
    ev = OrcParallelismCheck().collect(_ctx())
    ev_tasks = ev[0]
    assert ev_tasks.kind == "sql"
    assert "14" in ev_tasks.summary
    assert "20" in ev_tasks.summary
    assert ev_tasks.rows[0]["multi_task_jobs"] == 14


def test_collect_duration_evidence_content():
    ev = OrcParallelismCheck().collect(_ctx())
    ev_dur = ev[1]
    assert ev_dur.kind == "sql"
    assert "80" in ev_dur.summary
    assert ev_dur.rows[0]["total_runs"] == 80


def test_collect_note_mentions_dependency_limitation():
    ev = OrcParallelismCheck().collect(_ctx())
    note = ev[2]
    assert note.kind == "note"
    assert "dependenc" in note.summary.lower()


def test_collect_empty_sql_result_handled():
    ctx = AgentContext(
        assessment_id="t",
        layer="orchestration",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = OrcParallelismCheck().collect(ctx)
    assert ev[0].rows[0]["multi_task_jobs"] == 0
    assert ev[1].rows[0]["total_runs"] == 0


# --- judge() ---

def test_judge_met_verdict():
    f = OrcParallelismCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_partial_verdict():
    f = OrcParallelismCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL


def test_judge_confidence_capped_at_medium():
    resp = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "All jobs are multi-task."}'
    )
    f = OrcParallelismCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_two_sql_and_note():
    f = OrcParallelismCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert kinds.count("sql") == 2
    assert "note" in kinds


# --- llm=None ---

def test_no_llm_degrades_to_unassessed():
    f = OrcParallelismCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
