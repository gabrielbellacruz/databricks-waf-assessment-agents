from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.oe_experiment_tracking import ExperimentTrackingCheck

_Q = Question(
    id="ML-OE-02",
    pillar_id="operational-excellence",
    title="Automate experiment tracking",
    principle="Automate ML workflows for reproducibility",
)

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "High volume of automated run creation events from SPs."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "medium", "score": null,'
    ' "rationale": "No MLflow run events found."}'
)


def _ctx(
    *,
    llm_response: str | None = _LLM_MET,
    run_rows: list[dict] | None = None,
    caller_rows: list[dict] | None = None,
) -> AgentContext:
    sql_resp: dict[str, list[dict]] = {}
    # Needle for _RUN_VOLUME_SQL — "updateRun" appears only in the IN list there
    sql_resp["updateRun"] = run_rows if run_rows is not None else [
        {"action_name": "createRun", "event_count": 200},
        {"action_name": "logMetric", "event_count": 500},
    ]
    # Needle for _CALLER_SQL — distinct_callers alias appears only in this SQL
    sql_resp["distinct_callers"] = caller_rows if caller_rows is not None else [
        {"distinct_callers": 3, "sp_events": 180}
    ]
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(sql_resp),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_three_entries():
    ev = ExperimentTrackingCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_run_evidence_shows_total_events():
    ev = ExperimentTrackingCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "700" in ev[0].summary  # 200 + 500


def test_collect_caller_evidence_shows_sp_events():
    ev = ExperimentTrackingCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "3" in ev[1].summary  # distinct callers
    assert "180" in ev[1].summary  # sp_events
    assert ev[1].rows[0]["sp_events"] == 180


def test_collect_note_evidence_has_no_rows():
    ev = ExperimentTrackingCheck().collect(_ctx())
    note = ev[2]
    assert note.kind == "note"
    assert note.rows == []


def test_collect_empty_run_rows_produces_safe_summary():
    ctx = AgentContext(
        assessment_id="t2",
        layer="ml",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = ExperimentTrackingCheck().collect(ctx)
    assert "No MLflow run" in ev[0].summary


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_met_verdict():
    f = ExperimentTrackingCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    f = ExperimentTrackingCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET


def test_judge_confidence_capped_at_medium():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "Some automation."}'
    )
    f = ExperimentTrackingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_attached():
    f = ExperimentTrackingCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.sources


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = ExperimentTrackingCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
