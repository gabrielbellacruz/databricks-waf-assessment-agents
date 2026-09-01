from __future__ import annotations

from waf_agents.ai.checks.dg_lineage import AiLineageCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-DG-02",
    pillar_id="dg",
    title="Track lineage from source data to AI outputs",
    principle="Maintain an auditable chain from raw data to AI outputs",
)

# Distinct needles:
#   "lineage_audit_events" -> _AUDIT_SQL
#   "lineage_routines"     -> _ROUTINES_SQL
_FAKE = {
    "lineage_audit_events": [{"lineage_audit_events": 25, "distinct_users": 4}],
    "lineage_routines": [{"lineage_routines": 8, "routine_catalogs": 2}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_reports_audit_events():
    ev = AiLineageCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "25" in ev[0].summary
    assert "audit" in ev[0].summary.lower() or "event" in ev[0].summary.lower()


def test_collect_reports_routines():
    ev = AiLineageCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "8" in ev[1].summary


def test_collect_includes_limitation():
    ev = AiLineageCheck().collect(_ctx())
    assert ev[2].kind == "uc_metadata"
    assert "lineage" in ev[2].summary.lower() or "mlflow" in ev[2].summary.lower()


def test_collect_has_three_evidence_items():
    ev = AiLineageCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_rows_attached():
    ev = AiLineageCheck().collect(_ctx())
    assert ev[0].rows[0]["lineage_audit_events"] == 25
    assert ev[1].rows[0]["lineage_routines"] == 8


def test_collect_empty_sql_returns_zeros():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=FakeLlmClient(""),
    )
    ev = AiLineageCheck().collect(ctx)
    assert "0" in ev[0].summary


def test_judge_maps_llm_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "low",'
        ' "score": null, "rationale": "No ML audit events detected"}'
    )
    f = AiLineageCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.LOW


def test_judge_caps_high_to_medium():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Many lineage events"}'
    )
    f = AiLineageCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = AiLineageCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
