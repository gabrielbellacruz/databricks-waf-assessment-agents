from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.r_retries_timeouts import MlRetriesTimeoutsCheck

_Q = Question(
    id="ML-R-02",
    pillar_id="reliability",
    title="Configure retries and timeouts for training jobs",
    principle="Design for failure",
)

_JOB_ROWS = [
    {"total_runs": 80, "timed_out_runs": 5, "failed_runs": 8, "succeeded_runs": 67}
]


def _ctx(*, job_rows=None, llm_response: str | None = "") -> AgentContext:
    rows = job_rows if job_rows is not None else _JOB_ROWS
    return AgentContext(
        assessment_id="test-ml-r02",
        layer="ml",
        sql=FakeSqlClient({"job_run_timeline": rows}),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_summarises_run_outcomes():
    ev = MlRetriesTimeoutsCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "80" in ev[0].summary
    assert "5 TIMED_OUT" in ev[0].summary
    assert "8" in ev[0].summary  # failed


def test_collect_no_runs_returns_no_data_summary():
    ev = MlRetriesTimeoutsCheck().collect(_ctx(job_rows=[]))
    assert "No job runs found" in ev[0].summary


def test_collect_attaches_note_evidence():
    ev = MlRetriesTimeoutsCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "Manual confirmation" in ev[1].summary


def test_collect_evidence_has_rows():
    ev = MlRetriesTimeoutsCheck().collect(_ctx())
    assert ev[0].rows[0]["total_runs"] == 80
    assert ev[0].rows[0]["timed_out_runs"] == 5


def test_judge_maps_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium", "score": null,'
        ' "rationale": "Some TIMED_OUT seen"}'
    )
    f = MlRetriesTimeoutsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "low", "score": null,'
        ' "rationale": "No TIMED_OUT events"}'
    )
    f = MlRetriesTimeoutsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = MlRetriesTimeoutsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
