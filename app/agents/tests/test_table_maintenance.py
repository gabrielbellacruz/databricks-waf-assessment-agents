from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.table_maintenance import TableMaintenanceCheck

_Q = Question(
    id="STO-OE-01",
    pillar_id="operational-excellence",
    title="Automate table maintenance (OPTIMIZE, VACUUM)",
    principle="Keep tables healthy and compact through scheduled maintenance",
)

# Needle: "optimize_count" is a unique alias that only appears in _SQL.
_FAKE_RESPONSES = {
    "optimize_count": [{"optimize_count": 12, "vacuum_count": 5, "total": 3000}],
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
# collect() — evidence reflects OPTIMIZE/VACUUM counts
# ---------------------------------------------------------------------------


def test_collect_summary_includes_optimize_count():
    ev = TableMaintenanceCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "OPTIMIZE: 12" in ev[0].summary


def test_collect_summary_includes_vacuum_count():
    ev = TableMaintenanceCheck().collect(_ctx())
    assert "VACUUM: 5" in ev[0].summary


def test_collect_has_note_evidence():
    ev = TableMaintenanceCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "Predictive Optimization" in ev[1].summary


def test_collect_evidence_rows_carry_all_counts():
    ev = TableMaintenanceCheck().collect(_ctx())
    row = ev[0].rows[0]
    assert row["optimize_count"] == 12
    assert row["vacuum_count"] == 5
    assert row["total"] == 3000


def test_collect_no_rows_degrades_gracefully():
    ctx = AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(),  # no canned rows
        catalogs=["main"],
    )
    ev = TableMaintenanceCheck().collect(ctx)
    assert len(ev) == 2
    assert "No statements found" in ev[0].summary


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping and confidence cap
# ---------------------------------------------------------------------------


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some OPTIMIZE statements but no clear schedule"}'
    )
    f = TableMaintenanceCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if the model claims high.
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Regular OPTIMIZE and VACUUM commands found"}'
    )
    f = TableMaintenanceCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


# ---------------------------------------------------------------------------
# llm=None — unassessed fallback
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = TableMaintenanceCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached for explainability
