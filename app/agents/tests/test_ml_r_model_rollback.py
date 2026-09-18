from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Question, Verdict
from waf_agents.ml.checks.r_model_rollback import MlModelRollbackCheck

_Q = Question(
    id="ML-R-04",
    pillar_id="reliability",
    title="Enable rollback to a previous model version",
    principle="Test recovery procedures",
)

_AUDIT_ROWS = [
    {"action_name": "registerModelVersion", "event_count": 12},
    {"action_name": "setRegisteredModelAlias", "event_count": 4},
]

# The models query aggregates served_entities (entity_type='CUSTOM_MODEL') into
# a distinct-model count and a distinct model:version count; FakeSqlClient returns
# these canned rows in the shape the SELECT produces.
_MODEL_ROWS = [{"registered_model_count": 5, "model_version_count": 12}]


def _ctx(*, audit_rows=None, model_rows=None, llm_response: str | None = "") -> AgentContext:
    responses = {
        "registerModelVersion": audit_rows if audit_rows is not None else _AUDIT_ROWS,
        "served_entities": model_rows if model_rows is not None else _MODEL_ROWS,
    }
    return AgentContext(
        assessment_id="test-ml-r04",
        layer="ml",
        sql=FakeSqlClient(responses),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_summarises_audit_events():
    ev = MlModelRollbackCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "16" in ev[0].summary  # 12 + 4
    assert "registerModelVersion" in ev[0].summary


def test_collect_summarises_registered_models():
    ev = MlModelRollbackCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "5 custom model(s)" in ev[1].summary
    assert "12 version(s)" in ev[1].summary
    assert ev[1].rows[0]["registered_model_count"] == 5
    assert ev[1].rows[0]["model_version_count"] == 12


def test_collect_no_audit_events_reflects_uncertainty():
    ev = MlModelRollbackCheck().collect(_ctx(audit_rows=[]))
    assert "No model-lifecycle audit events" in ev[0].summary


def test_collect_attaches_limitation_note():
    ev = MlModelRollbackCheck().collect(_ctx())
    assert ev[2].kind == "note"
    assert "manual review" in ev[2].summary


def test_judge_maps_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "low", "score": null,'
        ' "rationale": "Some version events seen"}'
    )
    f = MlModelRollbackCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.sources


def test_no_llm_degrades_to_unassessed():
    f = MlModelRollbackCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
