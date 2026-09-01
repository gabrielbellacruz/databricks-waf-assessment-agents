from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.schema_change_control import SchemaChangeControlCheck

_Q = Question(
    id="STO-OE-03",
    pillar_id="operational-excellence",
    title="Manage schema changes to stored tables through change control",
    principle="Route schema changes through automation and review to prevent accidental drift",
)

# Needle: "sp_executed" is a unique column alias that only appears in _SQL.
_FAKE_RESPONSES = {
    "sp_executed": [{"alter_table_count": 10, "sp_executed": 8, "user_executed": 2}],
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
# collect() — evidence reflects ALTER TABLE origin breakdown
# ---------------------------------------------------------------------------


def test_collect_summary_includes_total_count():
    ev = SchemaChangeControlCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "10 ALTER TABLE" in ev[0].summary


def test_collect_summary_includes_sp_count():
    ev = SchemaChangeControlCheck().collect(_ctx())
    assert "8 run by service principals" in ev[0].summary


def test_collect_summary_includes_user_count():
    ev = SchemaChangeControlCheck().collect(_ctx())
    assert "2 run by interactive users" in ev[0].summary


def test_collect_evidence_rows_carry_all_counts():
    ev = SchemaChangeControlCheck().collect(_ctx())
    row = ev[0].rows[0]
    assert row["alter_table_count"] == 10
    assert row["sp_executed"] == 8
    assert row["user_executed"] == 2


def test_collect_no_alter_table_summary():
    ctx = AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(
            {"sp_executed": [{"alter_table_count": 0, "sp_executed": 0, "user_executed": 0}]}
        ),
        catalogs=["main"],
    )
    ev = SchemaChangeControlCheck().collect(ctx)
    assert "No ALTER TABLE" in ev[0].summary


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping and confidence cap
# ---------------------------------------------------------------------------


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Most schema changes run by service principals"}'
    )
    f = SchemaChangeControlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    # LLM confidence is capped at medium even if the model claims high.
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Mix of SP-driven and user-driven schema changes"}'
    )
    f = SchemaChangeControlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


# ---------------------------------------------------------------------------
# llm=None — unassessed fallback
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = SchemaChangeControlCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached for explainability
