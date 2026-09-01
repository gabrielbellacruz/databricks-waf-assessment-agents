from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.retries_timeouts import RetriesTimeoutsCheck

_Q = Question(
    id="ING-R-02",
    pillar_id="reliability",
    title="Configure ingestion jobs for automatic retries and timeouts",
    principle="Design for failure and recovery",
)

# Canned SQL rows: 20 runs total, 5 timed out, 3 failures.
_SQL_ROWS = [{"total_runs": 20, "timed_out_runs": 5, "failed_runs": 3}]

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "Timeouts observed; retries cannot be confirmed via system tables."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "medium", "score": null,'
    ' "rationale": "No TIMED_OUT runs detected; retry config unverifiable."}'
)


def _ctx(*, llm_response: str | None = _LLM_MET, runs: list[dict] | None = None) -> AgentContext:
    sql_rows = _SQL_ROWS if runs is None else runs
    return AgentContext(
        assessment_id="test-assessment",
        layer="ingestion",
        sql=FakeSqlClient({"job_run_timeline": sql_rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_two_evidence_entries():
    ev = RetriesTimeoutsCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_kind_and_content():
    ev = RetriesTimeoutsCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert "20" in sql_ev.summary  # total_runs
    assert "5" in sql_ev.summary  # timed_out_runs
    assert "3" in sql_ev.summary  # failed_runs
    assert sql_ev.rows[0]["total_runs"] == 20
    assert sql_ev.rows[0]["timed_out_runs"] == 5
    assert sql_ev.rows[0]["failed_runs"] == 3


def test_collect_note_evidence_kind_and_no_rows():
    ev = RetriesTimeoutsCheck().collect(_ctx())
    note_ev = ev[1]
    assert note_ev.kind == "note"
    assert note_ev.rows == []
    assert note_ev.ref == "https://docs.databricks.com/en/jobs/settings.html"


def test_collect_note_summary_mentions_jobs_api_limitation():
    ev = RetriesTimeoutsCheck().collect(_ctx())
    assert "Jobs-API" in ev[1].summary


def test_collect_no_runs_reports_zero():
    ev = RetriesTimeoutsCheck().collect(_ctx(runs=[]))
    assert ev[0].rows[0]["total_runs"] == 0
    assert ev[0].rows[0]["timed_out_runs"] == 0
    assert ev[0].rows[0]["failed_runs"] == 0
    assert "No job runs found" in ev[0].summary


def test_collect_zero_row_result_is_handled():
    """FakeSqlClient returns [] when no needle matches; must not raise."""
    ctx = AgentContext(
        assessment_id="t2",
        layer="ingestion",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = RetriesTimeoutsCheck().collect(ctx)
    assert ev[0].rows[0]["total_runs"] == 0


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_met_verdict_mapped():
    f = RetriesTimeoutsCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources  # evidence attached


def test_judge_not_met_verdict_mapped():
    f = RetriesTimeoutsCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_confidence_capped_at_medium_when_llm_claims_high():
    high_conf = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "some evidence"}'
    )
    f = RetriesTimeoutsCheck().run(_Q, _ctx(llm_response=high_conf))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_both_evidence_entries():
    f = RetriesTimeoutsCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = RetriesTimeoutsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached even without LLM
