from __future__ import annotations

from waf_agents.analytics.checks.r_metric_validation import MetricValidationCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-R-05",
    pillar_id="reliability",
    title="Validate metrics against expectations",
    principle="Ensure metrics are verified against known expectations before serving",
)

# Needles:
#   "validation_stmts"    -> _VALIDATION_SQL  (AS validation_stmts)
#   "constraint_type"     -> _CONSTRAINTS_SQL  (SELECT constraint_type ...)
_FAKE_RESPONSES = {
    "validation_stmts": [
        {"validation_stmts": 30, "total_stmts": 400}
    ],
    "constraint_type": [
        {"constraint_type": "CHECK", "cnt": 12},
        {"constraint_type": "NOT_NULL", "cnt": 40},
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
    ev = MetricValidationCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert ev[2].kind == "note"


def test_collect_validation_summary_contains_counts():
    ev = MetricValidationCheck().collect(_ctx())
    # 30/400 = 7.5%
    assert "30 of 400" in ev[0].summary
    assert "7.5%" in ev[0].summary


def test_collect_constraint_summary():
    ev = MetricValidationCheck().collect(_ctx())
    assert "CHECK=12" in ev[1].summary
    assert "NOT_NULL=40" in ev[1].summary


def test_collect_validation_evidence_rows():
    ev = MetricValidationCheck().collect(_ctx())
    assert ev[0].rows[0]["validation_stmts"] == 30
    assert ev[0].rows[0]["total_stmts"] == 400


def test_judge_maps_llm_verdict_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some validation patterns found, constraints exist"}'
    )
    f = MetricValidationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_no_llm_degrades_to_unassessed():
    f = MetricValidationCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
