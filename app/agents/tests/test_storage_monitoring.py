from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.storage_monitoring import StorageMonitoringCheck

_Q = Question(
    id="STO-OE-02",
    pillar_id="operational-excellence",
    title="Monitor storage growth and table health",
    principle="Track storage consumption trends to identify growth and health issues",
)

# Needle: "total_storage_dbu" is the unique column alias in _SQL.
_TREND_ROWS = [
    {"usage_date": "2026-07-01", "total_storage_dbu": 10.5},
    {"usage_date": "2026-07-02", "total_storage_dbu": 10.8},
    {"usage_date": "2026-07-03", "total_storage_dbu": 11.2},
]

_FAKE_RESPONSES = {
    "total_storage_dbu": _TREND_ROWS,
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence reflects billing trend rows
# ---------------------------------------------------------------------------


def test_collect_summary_shows_day_count():
    ev = StorageMonitoringCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "3 days" in ev[0].summary


def test_collect_summary_shows_trend_observable():
    ev = StorageMonitoringCheck().collect(_ctx())
    assert "trend is observable" in ev[0].summary


def test_collect_has_note_evidence():
    ev = StorageMonitoringCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "Per-table" in ev[1].summary or "per-table" in ev[1].summary


def test_collect_evidence_rows():
    ev = StorageMonitoringCheck().collect(_ctx())
    # Rows capped at 25; all 3 should be present.
    assert len(ev[0].rows) == 3


def test_collect_no_billing_rows_degrades_gracefully():
    ctx = AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(),  # no canned rows
        catalogs=["main"],
    )
    ev = StorageMonitoringCheck().collect(ctx)
    assert len(ev) == 2
    assert "No storage-SKU" in ev[0].summary


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping and confidence cap
# ---------------------------------------------------------------------------


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Storage trend visible but no table-level health monitoring"}'
    )
    f = StorageMonitoringCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if the model claims high.
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "low",'
        ' "score": null, "rationale": "No evidence of storage monitoring in place"}'
    )
    f = StorageMonitoringCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.LOW


# ---------------------------------------------------------------------------
# llm=None — unassessed fallback
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = StorageMonitoringCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached for explainability
