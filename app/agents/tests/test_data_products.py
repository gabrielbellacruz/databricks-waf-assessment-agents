from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.data_products import DataProductsCheck

_Q = Question(
    id="STO-IU-03",
    pillar_id="interoperability-usability",
    title="Publish curated stored data as reusable data products",
    principle="Make data discoverable, trusted, and reusable across the organisation",
)

# Needles are distinct AS aliases that don't appear in each other's SQL:
#   "described_tables"  -> _DESCRIBED_TABLES_SQL
#   "curated_schemas"   -> _CURATED_SCHEMAS_SQL
#   "certified_tables"  -> _CERTIFIED_TAGS_SQL
_FAKE_RESPONSES = {
    "described_tables": [{"total_tables": 200, "described_tables": 150}],
    "curated_schemas": [{"curated_schemas": 5, "curated_tables": 60}],
    "certified_tables": [{"certified_tables": 8}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_description_coverage():
    ev = DataProductsCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "150 of 200" in ev[0].summary
    # 150 / 200 = 75.0 %
    assert "75.0%" in ev[0].summary


def test_collect_curated_schemas():
    ev = DataProductsCheck().collect(_ctx())
    assert "60 table" in ev[1].summary
    assert "5 curated" in ev[1].summary


def test_collect_certified_tags():
    ev = DataProductsCheck().collect(_ctx())
    assert len(ev) == 3
    assert "8 table" in ev[2].summary


def test_collect_rows_attached():
    ev = DataProductsCheck().collect(_ctx())
    assert any(r.get("total_tables") == 200 for r in ev[0].rows)
    assert any(r.get("curated_schemas") == 5 for r in ev[1].rows)
    assert any(r.get("certified_tables") == 8 for r in ev[2].rows)


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "High description coverage and curated schemas present"}'
    )
    f = DataProductsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some curation present but incomplete"}'
    )
    f = DataProductsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = DataProductsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
