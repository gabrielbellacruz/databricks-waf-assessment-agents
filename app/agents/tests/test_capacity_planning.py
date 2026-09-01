from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.capacity_planning import CapacityPlanningCheck

_Q = Question(
    id="STO-OE-05",
    pillar_id="operational-excellence",
    title="Plan storage capacity and quotas",
    principle="Forecast storage growth and set quotas to avoid capacity surprises",
)

# Needle: "week_start" is a unique column alias that only appears in _SQL.
_WEEKLY_ROWS = [
    {"week_start": "2026-05-04", "total_storage_dbu": 50.0},
    {"week_start": "2026-05-11", "total_storage_dbu": 52.3},
    {"week_start": "2026-05-18", "total_storage_dbu": 55.1},
]

_FAKE_RESPONSES = {
    "week_start": _WEEKLY_ROWS,
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
# collect() — evidence reflects weekly billing trend rows
# ---------------------------------------------------------------------------


def test_collect_summary_shows_week_count():
    ev = CapacityPlanningCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "3 weeks" in ev[0].summary


def test_collect_summary_shows_trend_observable():
    ev = CapacityPlanningCheck().collect(_ctx())
    assert "weekly growth trend is observable" in ev[0].summary


def test_collect_has_note_evidence():
    ev = CapacityPlanningCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "quota" in ev[1].summary.lower()


def test_collect_evidence_rows():
    ev = CapacityPlanningCheck().collect(_ctx())
    assert len(ev[0].rows) == 3


def test_collect_no_billing_rows_degrades_gracefully():
    ctx = AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(),  # no canned rows
        catalogs=["main"],
    )
    ev = CapacityPlanningCheck().collect(ctx)
    assert len(ev) == 2
    assert "No storage-SKU" in ev[0].summary


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping and confidence cap
# ---------------------------------------------------------------------------


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Storage trend visible but no quota alerts configured"}'
    )
    f = CapacityPlanningCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if the model claims high.
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_unknown_verdict():
    resp = (
        '{"verdict": "unknown", "confidence": "low",'
        ' "score": null, "rationale": "Insufficient evidence to assess capacity planning"}'
    )
    f = CapacityPlanningCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


# ---------------------------------------------------------------------------
# llm=None — unassessed fallback
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = CapacityPlanningCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached for explainability
