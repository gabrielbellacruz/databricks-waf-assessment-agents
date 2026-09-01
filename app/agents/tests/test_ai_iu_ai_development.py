from __future__ import annotations

from waf_agents.ai.checks.iu_ai_development import AiDevelopmentAccelerationCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-IU-03",
    pillar_id="iu",
    title="Use AI capabilities to accelerate development",
    principle="Leverage AI tooling to speed up development workflows",
)

# Distinct needles:
#   "ai_assist_dbus" -> _BILLING_SQL
#   "ai_dev_events"  -> _AUDIT_SQL
_FAKE = {
    "ai_assist_dbus": [{"ai_assist_dbus": 6, "total_assist_dbus": 18.0}],
    "ai_dev_events": [{"ai_dev_events": 40, "distinct_users": 5}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_reports_billing_rows():
    ev = AiDevelopmentAccelerationCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "6" in ev[0].summary
    assert "18.00" in ev[0].summary
    assert "assistant" in ev[0].summary.lower() or "genie" in ev[0].summary.lower()


def test_collect_reports_audit_events():
    ev = AiDevelopmentAccelerationCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "40" in ev[1].summary
    assert "5" in ev[1].summary


def test_collect_includes_adoption_limitation():
    ev = AiDevelopmentAccelerationCheck().collect(_ctx())
    assert ev[2].kind == "uc_metadata"
    assert "assistant" in ev[2].summary.lower() or "audit" in ev[2].summary.lower()


def test_collect_has_three_evidence_items():
    ev = AiDevelopmentAccelerationCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_rows_attached():
    ev = AiDevelopmentAccelerationCheck().collect(_ctx())
    assert ev[0].rows[0]["ai_assist_dbus"] == 6
    assert ev[1].rows[0]["ai_dev_events"] == 40


def test_collect_empty_sql_returns_zeros():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=FakeLlmClient(""),
    )
    ev = AiDevelopmentAccelerationCheck().collect(ctx)
    assert "0" in ev[0].summary


def test_judge_maps_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "low",'
        ' "score": null, "rationale": "No AI tooling usage detected"}'
    )
    f = AiDevelopmentAccelerationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.LOW


def test_judge_maps_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Some Genie usage but limited Databricks Assistant"}'
    )
    f = AiDevelopmentAccelerationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_high_to_medium():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Extensive AI tool adoption"}'
    )
    f = AiDevelopmentAccelerationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = AiDevelopmentAccelerationCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
