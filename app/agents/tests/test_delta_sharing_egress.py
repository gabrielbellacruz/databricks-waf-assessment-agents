from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.delta_sharing_egress import DeltaSharingEgressCheck

_Q = Question(
    id="STO-CO-05",
    pillar_id="cost-optimization",
    title="Monitor Delta Sharing egress costs",
    principle="Understand and monitor egress costs incurred by Delta Sharing",
)

# Needles are distinct, non-overlapping substrings:
#   "NETWORK%"            -> _SQL_EGRESS_SKUS  (sku_name ILIKE '%NETWORK%')
#   "deltasharing_tables" -> _SQL_SHARING_TABLES  (AS deltasharing_tables)
_FAKE_RESPONSES = {
    "NETWORK%": [
        {"sku_name": "STANDARD_NETWORK_EGRESS", "records": 50, "total_usage": 12.5},
        {"sku_name": "DELTA_SHARING_EGRESS", "records": 20, "total_usage": 5.0},
    ],
    "deltasharing_tables": [{"deltasharing_tables": 3}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_reports_sku_count():
    ev = DeltaSharingEgressCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    # Two egress SKUs returned from fake
    assert "2 network/egress/sharing SKU(s)" in ev[0].summary


def test_collect_reports_total_billing_records():
    ev = DeltaSharingEgressCheck().collect(_ctx())
    # 50 + 20 = 70 total records
    assert "70 total billing record(s)" in ev[0].summary


def test_collect_sharing_tables_evidence():
    ev = DeltaSharingEgressCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "3 DELTASHARING-format table(s)" in ev[1].summary


def test_collect_note_mentions_attribution_limitation():
    ev = DeltaSharingEgressCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[2].kind == "note"
    assert "per-recipient" in ev[2].summary


def test_collect_egress_rows_attached():
    ev = DeltaSharingEgressCheck().collect(_ctx())
    sku_names = [r["sku_name"] for r in ev[0].rows]
    assert "STANDARD_NETWORK_EGRESS" in sku_names
    assert "DELTA_SHARING_EGRESS" in sku_names


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Egress SKUs present and sharing tables exist '
        'but per-recipient monitoring is not confirmed"}'
    )
    f = DeltaSharingEgressCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_unknown_when_no_evidence():
    resp = (
        '{"verdict": "unknown", "confidence": "low",'
        ' "score": null, "rationale": "No Delta Sharing tables; egress cannot be assessed"}'
    )
    f = DeltaSharingEgressCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_no_llm_degrades_to_unassessed():
    f = DeltaSharingEgressCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
