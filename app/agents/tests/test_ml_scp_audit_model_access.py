from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.scp_audit_model_access import AuditModelAccessCheck

_Q = Question(
    id="ML-SCP-05",
    pillar_id="security-compliance-privacy",
    title="Audit model access and deployment changes",
    principle="Capture and review ML lifecycle events in the audit trail",
)

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "Registry mutations and serving deployments both captured in audit."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "medium", "score": null,'
    ' "rationale": "No model audit events found."}'
)


def _ctx(
    *,
    llm_response: str | None = _LLM_MET,
    registry_rows: list[dict] | None = None,
    serving_rows: list[dict] | None = None,
) -> AgentContext:
    sql_resp: dict[str, list[dict]] = {}
    # Needle for _REGISTRY_AUDIT_SQL — "registeredModel" in action_name ILIKE
    sql_resp["registeredModel"] = registry_rows if registry_rows is not None else [
        {"action_name": "createModelVersion", "event_count": 6},
        {"action_name": "transitionModelVersionStage", "event_count": 3},
    ]
    # Needle for _SERVING_AUDIT_SQL — "createServingEndpoint" in action_name IN
    sql_resp["createServingEndpoint"] = serving_rows if serving_rows is not None else [
        {"action_name": "createServingEndpoint", "event_count": 2, "distinct_actors": 1},
        {"action_name": "updateServingEndpoint", "event_count": 5, "distinct_actors": 2},
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
    ev = AuditModelAccessCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_registry_evidence_shows_total_events():
    ev = AuditModelAccessCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "9" in ev[0].summary  # 6 + 3
    assert "2" in ev[0].summary  # 2 distinct action types


def test_collect_serving_evidence_shows_events():
    ev = AuditModelAccessCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "7" in ev[1].summary  # 2 + 5 total events


def test_collect_note_evidence_present():
    ev = AuditModelAccessCheck().collect(_ctx())
    note = ev[2]
    assert note.kind == "note"
    assert note.rows == []


def test_collect_note_mentions_review():
    ev = AuditModelAccessCheck().collect(_ctx())
    note_text = ev[2].summary.lower()
    assert "review" in note_text


def test_collect_no_registry_events_safe_summary():
    ctx = AgentContext(
        assessment_id="t2",
        layer="ml",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = AuditModelAccessCheck().collect(ctx)
    assert "No model-registry mutation events" in ev[0].summary
    assert "No serving endpoint mutation events" in ev[1].summary


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_met_verdict():
    f = AuditModelAccessCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    f = AuditModelAccessCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET


def test_judge_confidence_capped_at_medium():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "Partial audit coverage."}'
    )
    f = AuditModelAccessCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_registry_and_serving():
    f = AuditModelAccessCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert len(f.sources) == 3  # registry + serving + note


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = AuditModelAccessCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
