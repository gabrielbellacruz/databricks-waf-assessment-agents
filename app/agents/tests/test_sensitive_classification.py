from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.sensitive_classification import SensitiveClassificationCheck

_Q = Question(
    id="STO-DG-05",
    pillar_id="data-ai-governance",
    title="Classify sensitive stored data for masking",
    principle="Identify and label sensitive columns so masking policies can be applied",
)

# Needles are distinct, non-overlapping substrings of the three SQL strings:
#   "tagged_columns"          -> _COLUMN_TAG_COVERAGE_SQL (AS tagged_columns)
#   "sensitivity_tag_count"   -> _SENSITIVITY_TAGS_SQL    (AS sensitivity_tag_count)
#   "total_columns"           -> _TOTAL_COLUMNS_SQL        (AS total_columns)
_FAKE_RESPONSES = {
    "tagged_columns": [{"tagged_columns": 60, "tagged_tables": 10}],
    "sensitivity_tag_count": [{"sensitivity_tag_count": 35, "sensitivity_tagged_tables": 8}],
    "total_columns": [{"total_columns": 600}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# --- collect() tests ---

def test_collect_column_coverage_counts():
    ev = SensitiveClassificationCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "60 columns tagged" in ev[0].summary
    assert "10 tables" in ev[0].summary


def test_collect_column_coverage_percentage():
    ev = SensitiveClassificationCheck().collect(_ctx())
    # 60 / 600 = 10.0%
    assert "10.0%" in ev[0].summary
    assert "600 total UC columns" in ev[0].summary


def test_collect_sensitivity_tag_signal():
    ev = SensitiveClassificationCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "35 column tags indicate sensitivity" in ev[1].summary
    assert "8 tables" in ev[1].summary


def test_collect_evidence_has_rows():
    ev = SensitiveClassificationCheck().collect(_ctx())
    assert any(r.get("tagged_columns") == 60 for r in ev[0].rows)
    assert any(r.get("sensitivity_tag_count") == 35 for r in ev[1].rows)


def test_collect_returns_two_evidence_items():
    ev = SensitiveClassificationCheck().collect(_ctx())
    assert len(ev) == 2


# --- judge() tests ---

def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some PII columns tagged but coverage is low"}'
    )
    f = SensitiveClassificationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even when it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "No sensitivity tags found on columns"}'
    )
    f = SensitiveClassificationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = SensitiveClassificationCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
