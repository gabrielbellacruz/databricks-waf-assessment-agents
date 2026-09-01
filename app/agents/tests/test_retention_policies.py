from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.retention_policies import RetentionPoliciesCheck

_Q = Question(
    id="STO-DG-04",
    pillar_id="data-ai-governance",
    title="Define retention and lifecycle policies for stored data",
    principle="Enforce data lifecycle governance to meet compliance and cost objectives",
)

# Needles are distinct, non-overlapping substrings of the three SQL strings:
#   "tagged_tables"   -> _RETENTION_TABLE_TAGS_SQL   (AS tagged_tables)
#   "tagged_schemas"  -> _RETENTION_SCHEMA_TAGS_SQL  (AS tagged_schemas)
#   "total_tables"    -> _TOTAL_TABLES_SQL            (AS total_tables)
_FAKE_RESPONSES = {
    "tagged_tables": [{"tagged_tables": 15, "retention_tag_count": 22}],
    "tagged_schemas": [{"tagged_schemas": 4, "retention_schema_tag_count": 6}],
    "total_tables": [{"total_tables": 300}],
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

def test_collect_table_tag_counts():
    ev = RetentionPoliciesCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "15 tables" in ev[0].summary
    assert "22 individual retention tag entries" in ev[0].summary


def test_collect_table_tag_percentage():
    ev = RetentionPoliciesCheck().collect(_ctx())
    # 15 / 300 = 5.0%
    assert "5.0%" in ev[0].summary
    assert "300 UC tables" in ev[0].summary


def test_collect_schema_tag_counts():
    ev = RetentionPoliciesCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "4 schemas" in ev[1].summary


def test_collect_delta_property_note():
    ev = RetentionPoliciesCheck().collect(_ctx())
    assert ev[2].kind == "sql"
    assert "delta.deletedFileRetentionDuration" in ev[2].summary
    assert "NOT visible" in ev[2].summary


def test_collect_returns_three_evidence_items():
    ev = RetentionPoliciesCheck().collect(_ctx())
    assert len(ev) == 3


# --- judge() tests ---

def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some tables tagged but coverage is low"}'
    )
    f = RetentionPoliciesCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even when it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_unknown_when_no_tags():
    resp = (
        '{"verdict": "unknown", "confidence": "low",'
        ' "score": null, "rationale": "No retention tags found; Delta properties not visible"}'
    )
    f = RetentionPoliciesCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_no_llm_degrades_to_unassessed():
    f = RetentionPoliciesCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
