from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.iu_automl import MlAutomlCheck

_Q = Question(
    id="ML-IU-04",
    pillar_id="interoperability-usability",
    title="Use AutoML to accelerate baselines",
    principle="Leverage automated ML to reduce time-to-baseline",
)

# Needle "automl_events"       → _AUTOML_AUDIT_SQL
# Needle "automl_usage_events" → _AUTOML_BILLING_SQL
_FAKE_RESPONSES = {
    "automl_events": [{"automl_events": 12, "distinct_automl_users": 4}],
    "automl_usage_events": [{"automl_usage_events": 8, "automl_dbus": 320.5}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidence_items():
    ev = MlAutomlCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert ev[2].kind == "note"


def test_collect_audit_summary_mentions_events():
    ev = MlAutomlCheck().collect(_ctx())
    assert "12" in ev[0].summary
    assert "4" in ev[0].summary


def test_collect_billing_summary_mentions_records():
    ev = MlAutomlCheck().collect(_ctx())
    assert "8" in ev[1].summary


def test_collect_note_mentions_limitations():
    ev = MlAutomlCheck().collect(_ctx())
    note = ev[2].summary.lower()
    assert "automl" in note or "audit" in note


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium", "score": null,'
        ' "rationale": "AutoML events found"}'
    )
    f = MlAutomlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_unknown_when_no_events():
    resp = (
        '{"verdict": "unknown", "confidence": "low", "score": null,'
        ' "rationale": "No AutoML evidence"}'
    )
    f = MlAutomlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN


def test_no_llm_degrades_to_unassessed():
    f = MlAutomlCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
