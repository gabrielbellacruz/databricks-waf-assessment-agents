from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.iu_reusable_patterns import (
    ProcessingReusablePatternsCheck,
)

_Q = Question(
    id="PRO-IU-04",
    pillar_id="interoperability-usability",
    title="Reuse standard transformation patterns",
    principle="Build transformation pipelines from shared, blessed building blocks",
)

# SQL needle: "distinct_name_prefixes" (from the split(name,' ')[0] alias)
_FAKE_RESPONSES = {
    "distinct_name_prefixes": [
        {"total_jobs": 20, "distinct_name_prefixes": 4, "tagged_jobs": 15}
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_sql_evidence_shows_prefix_ratio():
    ev = ProcessingReusablePatternsCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    assert "20" in ev[0].summary  # total_jobs
    assert "4" in ev[0].summary   # distinct prefixes


def test_collect_note_warns_about_observability():
    ev = ProcessingReusablePatternsCheck().collect(_ctx())
    assert ev[1].kind == "note"
    assert "proxy" in ev[1].summary.lower()


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Low prefix ratio suggests templated jobs"}'
    )
    f = ProcessingReusablePatternsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "low",'
        ' "score": null, "rationale": "High distinct prefix count — one-off jobs"}'
    )
    f = ProcessingReusablePatternsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = ProcessingReusablePatternsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
