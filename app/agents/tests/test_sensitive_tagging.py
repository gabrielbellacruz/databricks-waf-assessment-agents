from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.sensitive_tagging import SensitiveTaggingCheck

_Q = Question(
    id="ING-DG-03",
    pillar_id="governance",
    title="Classify and tag sensitive data as it is ingested",
    principle="Protect data at rest and in transit",
)

# Needles are distinct, non-overlapping substrings of the three SQL strings:
#   "column_tags"  -> _COLUMN_TAGS_SQL  (FROM system.information_schema.column_tags)
#   "total_columns" -> _TOTAL_COLUMNS_SQL (AS total_columns)
#   "catalog_tags" -> _CATALOG_TAGS_SQL (FROM system.information_schema.catalog_tags)
_FAKE_RESPONSES = {
    "column_tags": [{"tagged_columns": 42, "tagged_tables": 7}],
    "total_columns": [{"total_columns": 420}],
    "catalog_tags": [{"catalog_tags": 3}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_counts_tagged_columns():
    ev = SensitiveTaggingCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "42 columns tagged" in ev[0].summary
    assert "7 tables" in ev[0].summary


def test_collect_shows_percentage():
    ev = SensitiveTaggingCheck().collect(_ctx())
    # 42 / 420 = 10%
    assert "10.0%" in ev[0].summary


def test_collect_catalog_tags_evidence():
    ev = SensitiveTaggingCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "sql"
    assert "3 catalog-level tags" in ev[1].summary


def test_collect_evidence_has_rows():
    ev = SensitiveTaggingCheck().collect(_ctx())
    # column_evidence rows include tag_rows and total_rows
    assert any(r.get("tagged_columns") == 42 for r in ev[0].rows)
    # catalog_evidence rows include catalog_rows
    assert any(r.get("catalog_tags") == 3 for r in ev[1].rows)


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some columns tagged but coverage is low"}'
    )
    f = SensitiveTaggingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "No columns are tagged"}'
    )
    f = SensitiveTaggingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = SensitiveTaggingCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
