from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.oe_mlops_standardization import MlopsStandardizationCheck

_Q = Question(
    id="ML-OE-01",
    pillar_id="operational-excellence",
    title="Standardize MLOps processes across teams",
    principle="Standardize and automate ML workflows",
)

# Distinct SQL needles for FakeSqlClient
_BREADTH_RESPONSES = [{"distinct_users": 8, "total_events": 150}]
_ACTION_RESPONSES = [
    {"action_name": "createRun", "event_count": 80},
    {"action_name": "logMetric", "event_count": 70},
]

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "Widespread MLflow usage across 8 users with diverse actions."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "medium", "score": null,'
    ' "rationale": "MLflow used but only by 2 users."}'
)


def _ctx(
    *,
    llm_response: str | None = _LLM_MET,
    breadth: list[dict] | None = None,
    actions: list[dict] | None = None,
) -> AgentContext:
    sql_resp: dict[str, list[dict]] = {}
    # Needle: "distinct_users" appears in _MLFLOW_BREADTH_SQL column alias
    sql_resp["distinct_users"] = breadth if breadth is not None else _BREADTH_RESPONSES
    # Needle: "action_name" + event_count appears in _MLFLOW_ACTIONS_SQL
    sql_resp["event_count"] = actions if actions is not None else _ACTION_RESPONSES
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


def test_collect_returns_three_evidence_entries():
    ev = MlopsStandardizationCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_breadth_evidence_kind_and_content():
    ev = MlopsStandardizationCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "150" in ev[0].summary
    assert "8" in ev[0].summary
    assert ev[0].rows[0]["distinct_users"] == 8
    assert ev[0].rows[0]["total_events"] == 150


def test_collect_action_evidence_reflects_distinct_types():
    ev = MlopsStandardizationCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "2" in ev[1].summary  # 2 distinct action types


def test_collect_note_evidence_has_no_rows():
    ev = MlopsStandardizationCheck().collect(_ctx())
    note = ev[2]
    assert note.kind == "note"
    assert note.rows == []


def test_collect_empty_sql_produces_safe_summary():
    ctx = AgentContext(
        assessment_id="t2",
        layer="ml",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = MlopsStandardizationCheck().collect(ctx)
    assert "No MLflow-related audit events" in ev[0].summary


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_met_verdict():
    f = MlopsStandardizationCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_partial_verdict():
    f = MlopsStandardizationCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_confidence_capped_at_medium_when_llm_claims_high():
    resp = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "Strong evidence."}'
    )
    f = MlopsStandardizationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_all_evidence_kinds():
    f = MlopsStandardizationCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = MlopsStandardizationCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
