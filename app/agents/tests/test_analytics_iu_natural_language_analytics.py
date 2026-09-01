from __future__ import annotations

from waf_agents.analytics.checks.iu_natural_language_analytics import NaturalLanguageAnalyticsCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Question, Verdict

_Q = Question(
    id="ANA-IU-04",
    pillar_id="interoperability-usability",
    title="Use natural-language analytics where helpful",
    principle="Natural-language interfaces lower the barrier to insights for non-technical users",
)

# Needles: 'ai_function_queries' matches _AI_FUNCTION_SQL,
#          'genie_style_queries' matches _GENIE_SIGNAL_SQL.
_FAKE_RESPONSES = {
    "ai_function_queries": [{"ai_function_queries": 35}],
    "genie_style_queries": [{"genie_style_queries": 5}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_ai_function_evidence():
    ev = NaturalLanguageAnalyticsCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "35" in ev[0].summary
    assert "ai_query" in ev[0].summary.lower() or "ai" in ev[0].summary.lower()


def test_collect_genie_evidence():
    ev = NaturalLanguageAnalyticsCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "5" in ev[1].summary


def test_collect_limitation_evidence():
    ev = NaturalLanguageAnalyticsCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[2].kind == "uc_metadata"
    assert "genie" in ev[2].summary.lower()


def test_judge_partial():
    resp = (
        '{"verdict": "partial", "confidence": "low",'
        ' "score": null, "rationale": "Some AI functions in use but limited adoption"}'
    )
    f = NaturalLanguageAnalyticsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL


def test_judge_unknown_when_no_signal():
    resp = (
        '{"verdict": "unknown", "confidence": "low",'
        ' "score": null, "rationale": "No NL analytics signal detected"}'
    )
    f = NaturalLanguageAnalyticsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN


def test_no_llm_degrades_to_unassessed():
    f = NaturalLanguageAnalyticsCheck().run(_Q, _ctx(llm_response=None))
    assert f.auto_assessable is False
    assert f.sources
