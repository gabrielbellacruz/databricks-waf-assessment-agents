from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.dg_masking_filters import ProcessingMaskingFiltersCheck

_Q = Question(
    id="PRO-DG-04",
    pillar_id="data-ai-governance",
    title="Apply masking/row filters within processing",
    principle="Enforce data-access policies at the processing layer",
)

# Distinct SQL needle: "SET ROW FILTER"
_FAKE_RESPONSES = {
    "SET ROW FILTER": [
        {"masking_stmts": 8, "drop_masking_stmts": 1, "total_stmts": 500}
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


def test_collect_includes_masking_statement_count():
    ev = ProcessingMaskingFiltersCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    assert "8" in ev[0].summary  # masking_stmts


def test_collect_note_warns_about_observability_limit():
    ev = ProcessingMaskingFiltersCheck().collect(_ctx())
    assert ev[1].kind == "note"
    assert "observable" in ev[1].summary.lower() or "service principal" in ev[1].summary.lower()


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Multiple masking DDL statements found"}'
    )
    f = ProcessingMaskingFiltersCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "low",'
        ' "score": null, "rationale": "No masking or row-filter statements found"}'
    )
    f = ProcessingMaskingFiltersCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = ProcessingMaskingFiltersCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
