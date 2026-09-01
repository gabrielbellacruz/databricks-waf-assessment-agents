from __future__ import annotations

from waf_agents.core.clients import (
    AgentContext,
    FakeLlmClient,
    FakeSqlClient,
)
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.certified_partner_tools import CertifiedPartnerToolsCheck

_Q = Question(
    id="ING-IU-04",
    pillar_id="interoperability-usability",
    title="Use certified partner tools for ingestion",
    principle="Use Databricks-certified partner tools for ingestion workloads",
)

_LINEAGE_ROWS = [
    {"source_type": "JDBC", "n": 42},
    {"source_type": "S3", "n": 15},
    {"source_type": "KAFKA", "n": 7},
]

# Canned LLM response reflecting the expected lean toward unknown.
_LLM_UNKNOWN = (
    '{"verdict": "unknown", "confidence": "low", "score": null, '
    '"rationale": "Source types observed but certification status cannot be confirmed"}'
)


def _ctx(*, llm_response: str | None = _LLM_UNKNOWN) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient({"table_lineage": _LINEAGE_ROWS}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_produces_two_evidence_entries():
    ev = CertifiedPartnerToolsCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_first_entry_is_sql_with_rows():
    ev = CertifiedPartnerToolsCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert ev[0].rows == _LINEAGE_ROWS


def test_collect_second_entry_is_note_with_no_rows():
    ev = CertifiedPartnerToolsCheck().collect(_ctx())
    assert ev[1].kind == "note"
    assert ev[1].rows == []


def test_collect_sql_hits_table_lineage():
    """FakeSqlClient is keyed on 'table_lineage'; evidence should carry its rows."""
    sql_client = FakeSqlClient({"table_lineage": _LINEAGE_ROWS})
    ctx = AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=sql_client,
        catalogs=["main"],
    )
    ev = CertifiedPartnerToolsCheck().collect(ctx)
    assert any("table_lineage" in call for call in sql_client.calls)
    assert ev[0].rows == _LINEAGE_ROWS


def test_judge_maps_unknown_low_from_llm():
    f = CertifiedPartnerToolsCheck().run(_Q, _ctx(llm_response=_LLM_UNKNOWN))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
    assert f.sources  # evidence is always attached for explainability


def test_judge_maps_met_verdict_and_caps_high_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high", "score": null, '
        '"rationale": "Certified Fivetran connector clearly identified"}'
    )
    f = CertifiedPartnerToolsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = CertifiedPartnerToolsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is attached even when llm is absent
    assert f.sources
