from __future__ import annotations

from waf_agents.ai.checks.dg_prompt_governance import AiPromptGovernanceCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-DG-05",
    pillar_id="dg",
    title="Govern and version prompts and configurations",
    principle="Treat prompts as versioned, governed assets with change history",
)

# Distinct needles:
#   "prompt_func_count"    -> _ROUTINES_SQL
#   "prompt_audit_events"  -> _AUDIT_SQL
_FAKE = {
    "prompt_func_count": [{"prompt_func_count": 5, "routine_catalogs": 2}],
    "prompt_audit_events": [{"prompt_audit_events": 18, "distinct_users": 3}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_reports_prompt_functions():
    ev = AiPromptGovernanceCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "5" in ev[0].summary
    assert "prompt" in ev[0].summary.lower() or "function" in ev[0].summary.lower()


def test_collect_reports_audit_events():
    ev = AiPromptGovernanceCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "18" in ev[1].summary
    assert "event" in ev[1].summary.lower() or "endpoint" in ev[1].summary.lower()


def test_collect_includes_prompt_limitation():
    ev = AiPromptGovernanceCheck().collect(_ctx())
    assert ev[2].kind == "uc_metadata"
    assert "notebook" in ev[2].summary.lower() or "uc" in ev[2].summary.lower()


def test_collect_has_three_evidence_items():
    ev = AiPromptGovernanceCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_rows_attached():
    ev = AiPromptGovernanceCheck().collect(_ctx())
    assert ev[0].rows[0]["prompt_func_count"] == 5
    assert ev[1].rows[0]["prompt_audit_events"] == 18


def test_collect_empty_sql_returns_zeros():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=FakeLlmClient(""),
    )
    ev = AiPromptGovernanceCheck().collect(ctx)
    assert "0" in ev[0].summary


def test_judge_maps_unknown_with_no_signal():
    resp = (
        '{"verdict": "unknown", "confidence": "low",'
        ' "score": null, "rationale": "Insufficient evidence for prompt governance"}'
    )
    f = AiPromptGovernanceCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Prompt functions registered in UC with audit trail"}'
    )
    f = AiPromptGovernanceCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_high_to_medium():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Comprehensive prompt governance"}'
    )
    f = AiPromptGovernanceCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = AiPromptGovernanceCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
