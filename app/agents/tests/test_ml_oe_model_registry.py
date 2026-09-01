from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.oe_model_registry import ModelRegistryCheck

_Q = Question(
    id="ML-OE-04",
    pillar_id="operational-excellence",
    title="Use a model registry to manage the model lifecycle",
    principle="Manage the full ML model lifecycle",
)

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "Active model registry usage with stage transitions."}'
)
_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "medium", "score": null,'
    ' "rationale": "Models registered but no stage transitions found."}'
)


def _ctx(
    *,
    llm_response: str | None = _LLM_MET,
    action_rows: list[dict] | None = None,
    uc_rows: list[dict] | None = None,
) -> AgentContext:
    sql_resp: dict[str, list[dict]] = {}
    # Needle for _REGISTRY_ACTIONS_SQL — action_name + event_count
    sql_resp["registeredModel"] = action_rows if action_rows is not None else [
        {"action_name": "createModelVersion", "event_count": 12},
        {"action_name": "transitionModelVersionStage", "event_count": 5},
    ]
    # Needle for _UC_MODELS_SQL — total_models
    sql_resp["total_models"] = uc_rows if uc_rows is not None else [
        {"total_models": 6, "model_catalogs": 2}
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
    ev = ModelRegistryCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_registry_evidence_shows_event_count():
    ev = ModelRegistryCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "17" in ev[0].summary  # 12 + 5
    assert "2" in ev[0].summary   # distinct action types


def test_collect_uc_evidence_shows_model_count():
    ev = ModelRegistryCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "6" in ev[1].summary
    assert ev[1].rows[0]["total_models"] == 6


def test_collect_note_evidence_present():
    ev = ModelRegistryCheck().collect(_ctx())
    note = ev[2]
    assert note.kind == "note"
    assert note.rows == []


def test_collect_empty_returns_safe_summary():
    ctx = AgentContext(
        assessment_id="t2",
        layer="ml",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = ModelRegistryCheck().collect(ctx)
    assert "No model-registry audit events" in ev[0].summary


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_met_verdict():
    f = ModelRegistryCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_partial_verdict():
    f = ModelRegistryCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL


def test_judge_confidence_capped_at_medium():
    resp = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "Strong evidence."}'
    )
    f = ModelRegistryCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_attached():
    f = ModelRegistryCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.sources


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = ModelRegistryCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
