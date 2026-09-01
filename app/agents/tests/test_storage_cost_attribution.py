from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.storage_cost_attribution import StorageCostAttributionCheck

_Q = Question(
    id="STO-CO-04",
    pillar_id="cost-optimization",
    title="Attribute storage cost by owner",
    principle="Tag storage usage so cost can be attributed to owning teams",
)

# Needle: "STORAGE%" is a unique substring of the SQL (from "AND sku_name ILIKE '%STORAGE%'").
# It does not appear in any other query this check issues.
_FAKE_RESPONSES = {
    "STORAGE%": [{"total": 200, "tagged": 160}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_reports_tagged_and_total():
    ev = StorageCostAttributionCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "160 of 200" in ev[0].summary


def test_collect_shows_tag_percentage():
    ev = StorageCostAttributionCheck().collect(_ctx())
    # 160 / 200 = 80.0%
    assert "80.0%" in ev[0].summary


def test_collect_mentions_storage_skus():
    ev = StorageCostAttributionCheck().collect(_ctx())
    assert "STORAGE" in ev[0].summary


def test_collect_evidence_has_rows():
    ev = StorageCostAttributionCheck().collect(_ctx())
    row = ev[0].rows[0]
    assert row["total"] == 200
    assert row["tagged"] == 160
    assert row["tagged_pct"] == 80.0


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "80% of storage records carry custom tags"}'
    )
    f = StorageCostAttributionCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Some storage records tagged but coverage incomplete"}'
    )
    f = StorageCostAttributionCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = StorageCostAttributionCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
