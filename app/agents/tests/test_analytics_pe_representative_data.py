from __future__ import annotations

from waf_agents.analytics.checks.pe_representative_data import RepresentativeDataCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-PE-04",
    pillar_id="performance-efficiency",
    title="Test analytics on production-representative data",
    principle="Validate analytics query performance against realistic data volumes",
)

# Needles:
#   "schema_name"        -> _SCHEMA_SQL      (SELECT schema_name, catalog_name ...)
#   "dev_env_queries"    -> _DEV_QUERY_SQL   (AS dev_env_queries)
_FAKE_RESPONSES = {
    "schema_name": [
        {"schema_name": "prod_analytics", "catalog_name": "main"},
        {"schema_name": "dev_analytics", "catalog_name": "main"},
        {"schema_name": "staging_reports", "catalog_name": "main"},
        {"schema_name": "default", "catalog_name": "main"},
    ],
    "dev_env_queries": [
        {"dev_env_queries": 80, "total_queries": 500}
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidences():
    ev = RepresentativeDataCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert ev[2].kind == "note"


def test_collect_schema_summary_counts_dev_schemas():
    ev = RepresentativeDataCheck().collect(_ctx())
    # 4 schemas found, 2 are dev/test/staging (dev_analytics, staging_reports)
    assert "4 schema(s)" in ev[0].summary
    assert "2 appear to be dev/test/staging" in ev[0].summary


def test_collect_dev_query_summary():
    ev = RepresentativeDataCheck().collect(_ctx())
    # 80/500 = 16.0%
    assert "80 of 500" in ev[1].summary
    assert "16.0%" in ev[1].summary


def test_collect_schema_evidence_rows_show_dev_schemas():
    ev = RepresentativeDataCheck().collect(_ctx())
    # rows should only contain dev/test/staging schemas
    schema_names = [r["schema_name"] for r in ev[0].rows]
    assert "dev_analytics" in schema_names
    assert "staging_reports" in schema_names
    assert "prod_analytics" not in schema_names


def test_judge_maps_llm_verdict_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Dev environments exist but data volumes unknown"}'
    )
    f = RepresentativeDataCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_no_llm_degrades_to_unassessed():
    f = RepresentativeDataCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
