from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.schema_enforcement import SchemaEnforcementCheck

_Q = Question(
    id="ING-R-04",
    pillar_id="reliability",
    title="Enforce schema on incoming data",
    principle="Protect data quality at the boundary",
)

_TABLE_ROWS = [{"total_tables": 40, "delta_tables": 35}]
_CONSTRAINT_ROWS = [{"declared_constraints": 12}]


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient(
            {
                "information_schema.tables": _TABLE_ROWS,
                "table_constraints": _CONSTRAINT_ROWS,
            }
        ),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_produces_sql_and_note_evidence():
    ev = SchemaEnforcementCheck().collect(_ctx())
    kinds = [e.kind for e in ev]
    assert "sql" in kinds
    assert "note" in kinds


def test_collect_sql_evidence_includes_counts():
    ev = SchemaEnforcementCheck().collect(_ctx())
    sql_ev = next(e for e in ev if e.kind == "sql")
    assert "35 of 40" in sql_ev.summary
    assert "12" in sql_ev.summary
    assert sql_ev.rows[0]["total_tables"] == 40
    assert sql_ev.rows[0]["delta_tables"] == 35
    assert sql_ev.rows[0]["declared_constraints"] == 12


def test_collect_note_evidence_has_empty_rows():
    ev = SchemaEnforcementCheck().collect(_ctx())
    note_ev = next(e for e in ev if e.kind == "note")
    assert note_ev.rows == []
    assert "baseline proxy" in note_ev.summary


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "mostly Delta tables"}'
    )
    f = SchemaEnforcementCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_no_llm_degrades_to_unassessed():
    f = SchemaEnforcementCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # evidence is still attached for explainability
    assert f.sources
