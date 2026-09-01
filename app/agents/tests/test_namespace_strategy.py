from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.namespace_strategy import NamespaceStrategyCheck

_Q = Question(
    id="STO-DG-01",
    pillar_id="data-ai-governance",
    title="Organize storage with a Unity Catalog namespace strategy",
    principle="Govern data placement with a coherent catalog/schema hierarchy",
)

# Needles are distinct, non-overlapping substrings of the three SQL strings:
#   "catalogs"        -> _CATALOG_COUNT_SQL   (FROM system.information_schema.catalogs)
#   "schemata"        -> _SCHEMAS_PER_CATALOG_SQL
#   "table_catalog"   -> _TABLES_PER_CATALOG_SQL (GROUP BY table_catalog)
_FAKE_RESPONSES = {
    "catalogs": [{"catalog_count": 4}],
    "schemata": [
        {"catalog_name": "prod", "schema_count": 12},
        {"catalog_name": "dev", "schema_count": 5},
    ],
    "table_catalog": [
        {"table_catalog": "prod", "table_count": 200},
        {"table_catalog": "dev", "table_count": 50},
        {"table_catalog": "hive_metastore", "table_count": 30},
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["prod", "dev"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# --- collect() tests ---

def test_collect_catalog_count():
    ev = NamespaceStrategyCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "4 Unity Catalog catalogs" in ev[0].summary


def test_collect_schema_distribution():
    ev = NamespaceStrategyCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    # 2 catalogs have schemas in fake data
    assert "2 catalog(s)" in ev[1].summary
    assert len(ev[1].rows) == 2


def test_collect_hive_metastore_share():
    ev = NamespaceStrategyCheck().collect(_ctx())
    # 30 hive / 280 total = ~10.7%
    assert "30 tables still in hive_metastore" in ev[2].summary
    assert "280 total" in ev[2].summary


def test_collect_returns_three_evidence_items():
    ev = NamespaceStrategyCheck().collect(_ctx())
    assert len(ev) == 3


# --- judge() tests ---

def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some catalogs present but hive_metastore still used"}'
    )
    f = NamespaceStrategyCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Well-structured catalog hierarchy"}'
    )
    f = NamespaceStrategyCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = NamespaceStrategyCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
