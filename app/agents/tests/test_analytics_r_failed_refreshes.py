from __future__ import annotations

from waf_agents.analytics.checks.r_failed_refreshes import FailedRefreshesCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-R-04",
    pillar_id="reliability",
    title="Detect and recover from failed dataset refreshes",
    principle="Ensure refresh failures are detected and recovered automatically",
)

# Needles:
#   "failed_stmts"        -> _FAILED_REFRESH_SQL  (AS failed_stmts)
#   "warehouse_events"    -> _WAREHOUSE_ERROR_SQL  (FROM system.compute.warehouse_events)
_FAKE_RESPONSES = {
    "failed_stmts": [
        {"failed_stmts": 4, "succeeded_stmts": 46, "total_stmts": 50}
    ],
    "warehouse_events": [
        {"event_type": "CREATE_ERROR", "cnt": 2},
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidences():
    ev = FailedRefreshesCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert ev[2].kind == "note"


def test_collect_refresh_summary_contains_failure_count():
    ev = FailedRefreshesCheck().collect(_ctx())
    assert "50 total" in ev[0].summary
    assert "46 succeeded" in ev[0].summary
    assert "4 failed" in ev[0].summary
    # 4/50 = 8.0%
    assert "8.0%" in ev[0].summary


def test_collect_error_events_summary():
    ev = FailedRefreshesCheck().collect(_ctx())
    assert "CREATE_ERROR=2" in ev[1].summary


def test_collect_refresh_evidence_rows():
    ev = FailedRefreshesCheck().collect(_ctx())
    assert ev[0].rows[0]["failed_stmts"] == 4
    assert ev[0].rows[0]["succeeded_stmts"] == 46


def test_judge_maps_llm_verdict_caps_confidence():
    resp = (
        '{"verdict": "not_met", "confidence": "high",'
        ' "score": null, "rationale": "8% failure rate with no alerting evidence"}'
    )
    f = FailedRefreshesCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_no_llm_degrades_to_unassessed():
    f = FailedRefreshesCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
