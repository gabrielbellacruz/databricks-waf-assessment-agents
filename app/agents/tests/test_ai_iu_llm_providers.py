from __future__ import annotations

from waf_agents.ai.checks.iu_llm_providers import AiLlmProvidersCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-IU-02",
    pillar_id="iu",
    title="Streamline management of multiple LLM providers",
    principle="Centralise LLM provider management through AI Gateway",
)

# Distinct needles:
#   "distinct_llm_providers" -> _GATEWAY_SQL
#   "ext_model_dbus"         -> _BILLING_SQL
_FAKE = {
    "distinct_llm_providers": [{"distinct_llm_providers": 4, "total_gateway_calls": 5000}],
    "ext_model_dbus": [{"ext_model_dbus": 12.3, "internal_model_dbus": 88.7}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_reports_gateway_providers():
    ev = AiLlmProvidersCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "4" in ev[0].summary
    assert "endpoint" in ev[0].summary.lower() or "gateway" in ev[0].summary.lower()


def test_collect_reports_billing_split():
    ev = AiLlmProvidersCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "12.30" in ev[1].summary or "12.3" in ev[1].summary
    assert "88.70" in ev[1].summary or "88.7" in ev[1].summary


def test_collect_includes_provider_limitation():
    ev = AiLlmProvidersCheck().collect(_ctx())
    assert ev[2].kind == "uc_metadata"
    assert "provider" in ev[2].summary.lower()


def test_collect_has_three_evidence_items():
    ev = AiLlmProvidersCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_rows_attached():
    ev = AiLlmProvidersCheck().collect(_ctx())
    assert ev[0].rows[0]["distinct_llm_providers"] == 4
    assert ev[1].rows[0]["ext_model_dbus"] == 12.3


def test_collect_empty_sql_returns_zeros():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=FakeLlmClient(""),
    )
    ev = AiLlmProvidersCheck().collect(ctx)
    assert "0" in ev[0].summary


def test_judge_maps_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Multiple providers via AI Gateway"}'
    )
    f = AiLlmProvidersCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_high_to_medium():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Clear multi-provider setup"}'
    )
    f = AiLlmProvidersCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = AiLlmProvidersCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
