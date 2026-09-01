from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.iu_ai_assistance import ProcessingAiAssistanceCheck

_Q = Question(
    id="PRO-IU-05",
    pillar_id="interoperability-usability",
    title="Use AI assistance to build transformations",
    principle="Leverage AI capabilities to accelerate and improve transformation development",
)

# SQL needle: "ai_query(" (from the ILIKE '%ai_query(%' pattern)
_FAKE_RESPONSES = {
    "ai_query(": [{"ai_sql_stmts": 15, "total_stmts": 1200}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_shows_ai_statement_count():
    ev = ProcessingAiAssistanceCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    assert "15" in ev[0].summary  # ai_sql_stmts


def test_collect_note_warns_about_notebook_gap():
    ev = ProcessingAiAssistanceCheck().collect(_ctx())
    assert ev[1].kind == "note"
    # Note should mention that notebook-level AI usage is not observable
    assert "notebook" in ev[1].summary.lower() or "observable" in ev[1].summary.lower()


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some AI SQL functions used but limited scope"}'
    )
    f = ProcessingAiAssistanceCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Broad AI SQL function usage detected"}'
    )
    f = ProcessingAiAssistanceCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET


def test_no_llm_degrades_to_unassessed():
    f = ProcessingAiAssistanceCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
