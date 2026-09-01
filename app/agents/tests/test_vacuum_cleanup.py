from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.vacuum_cleanup import VacuumCleanupCheck

_Q = Question(
    id="STO-CO-02",
    pillar_id="cost-optimization",
    title="Vacuum and clean up obsolete stored files",
    principle="Remove obsolete Delta files to reduce storage cost",
)

# Needle: "vacuum_statements" matches the COUNT alias in _SQL_VACUUM.
# This substring does not appear in any other query this check issues.
_FAKE_RESPONSES = {
    "vacuum_statements": [{"vacuum_statements": 15}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_reports_vacuum_count():
    ev = VacuumCleanupCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "15 VACUUM statement(s)" in ev[0].summary


def test_collect_mentions_window():
    ev = VacuumCleanupCheck().collect(_ctx())
    assert "90 days" in ev[0].summary


def test_collect_note_mentions_predictive_optimization():
    ev = VacuumCleanupCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "Predictive Optimization" in ev[1].summary


def test_collect_evidence_has_rows():
    ev = VacuumCleanupCheck().collect(_ctx())
    assert ev[0].rows == [{"vacuum_statements": 15}]


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some VACUUM statements found but infrequent"}'
    )
    f = VacuumCleanupCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "No VACUUM statements found in the window"}'
    )
    f = VacuumCleanupCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = VacuumCleanupCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
