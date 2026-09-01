from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.oe_model_monitoring import ModelMonitoringCheck

_Q = Question(
    id="ML-OE-05",
    pillar_id="operational-excellence",
    title="Monitor models for drift and performance",
    principle="Detect model quality degradation early",
)

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "Lakehouse Monitoring SKU consumption and audit events found."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "medium", "score": null,'
    ' "rationale": "No monitoring infrastructure found."}'
)


def _ctx(
    *,
    llm_response: str | None = _LLM_MET,
    billing_rows: list[dict] | None = None,
    audit_rows: list[dict] | None = None,
) -> AgentContext:
    sql_resp: dict[str, list[dict]] = {}
    # Needle for _MONITORING_BILLING_SQL — sku_name + total_dbus
    sql_resp["MONITOR"] = billing_rows if billing_rows is not None else [
        {"sku_name": "LAKEHOUSE_MONITORING", "total_dbus": 24.5}
    ]
    # Needle for _MONITORING_AUDIT_SQL — "monitor" in action_name
    sql_resp["createMonitor"] = audit_rows if audit_rows is not None else [
        {"action_name": "createMonitor", "event_count": 3},
        {"action_name": "runRefresh", "event_count": 10},
    ]
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(sql_resp),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_three_entries():
    ev = ModelMonitoringCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_billing_evidence_shows_dbus():
    ev = ModelMonitoringCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "1" in ev[0].summary  # 1 SKU
    assert "24.5" in ev[0].summary


def test_collect_audit_evidence_shows_event_count():
    ev = ModelMonitoringCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "13" in ev[1].summary  # 3 + 10
    assert "2" in ev[1].summary  # 2 distinct action types


def test_collect_note_evidence_present():
    ev = ModelMonitoringCheck().collect(_ctx())
    note = ev[2]
    assert note.kind == "note"
    assert note.rows == []


def test_collect_no_billing_produces_safe_summary():
    ctx = AgentContext(
        assessment_id="t2",
        layer="ml",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = ModelMonitoringCheck().collect(ctx)
    assert "No Lakehouse Monitoring SKU" in ev[0].summary


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_met_verdict():
    f = ModelMonitoringCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    f = ModelMonitoringCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET


def test_judge_confidence_capped_at_medium():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "Partial evidence."}'
    )
    f = ModelMonitoringCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_billing_and_audit():
    f = ModelMonitoringCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = ModelMonitoringCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
