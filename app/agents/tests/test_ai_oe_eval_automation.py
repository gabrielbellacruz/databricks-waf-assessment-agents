from __future__ import annotations

from waf_agents.ai.checks.oe_eval_automation import EvalAutomationCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-OE-02",
    pillar_id="oe",
    title="Automate LLM evaluation in the pipeline",
    principle="Integrate evaluation into the delivery process",
)

# Needles: system.access.audit has no user_type, so service principals are
# approximated by user_identity.email NOT LIKE '%@%' in _SP_SERVING_SQL;
# "job_run_timeline" is in _JOB_RUNS_SQL.
_FAKE = {
    "user_identity.email": [{"sp_serving_calls": 45, "distinct_principals": 3}],
    "job_run_timeline": [{"total_runs": 120, "distinct_jobs": 8}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_sp_evidence():
    ev = EvalAutomationCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "45" in ev[0].summary
    assert "3" in ev[0].summary


def test_collect_job_evidence():
    ev = EvalAutomationCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "120" in ev[1].summary
    assert "8" in ev[1].summary


def test_collect_note_evidence():
    ev = EvalAutomationCheck().collect(_ctx())
    assert ev[2].kind == "note"
    assert "NOT" in ev[2].summary or "not distinguishable" in ev[2].summary


def test_collect_empty_sp():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({"job_run_timeline": [{"total_runs": 5, "distinct_jobs": 1}]}),
        llm=FakeLlmClient(""),
    )
    ev = EvalAutomationCheck().collect(ctx)
    assert "No service-principal" in ev[0].summary


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "No evidence of automated eval pipelines"}'
    )
    f = EvalAutomationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_unknown_on_no_evidence():
    resp = (
        '{"verdict": "unknown", "confidence": "low",'
        ' "score": null, "rationale": "Cannot distinguish eval from production jobs"}'
    )
    f = EvalAutomationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_no_llm_degrades_to_unassessed():
    f = EvalAutomationCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
