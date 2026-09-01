from __future__ import annotations

from waf_agents.analytics.checks.pe_table_layout import TableLayoutCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-PE-02",
    pillar_id="performance-efficiency",
    title="Optimize table layout for analytics queries",
    principle="Ensure tables are laid out to minimize data scanned by analytics queries",
)

# Needles:
#   "optimize_stmts"  -> _LAYOUT_SQL   (AS optimize_stmts)
#   "delta_tables"    -> _DELTA_TABLES_SQL  (AS delta_tables)
_FAKE_RESPONSES = {
    "optimize_stmts": [
        {"optimize_stmts": 20, "zorder_stmts": 8, "cluster_by_stmts": 3, "total_stmts": 600}
    ],
    "delta_tables": [
        {"total_tables": 100, "delta_tables": 85}
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidences():
    ev = TableLayoutCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert ev[2].kind == "note"


def test_collect_layout_summary_contains_command_counts():
    ev = TableLayoutCheck().collect(_ctx())
    assert "OPTIMIZE=20" in ev[0].summary
    assert "ZORDER BY=8" in ev[0].summary
    assert "CLUSTER BY=3" in ev[0].summary
    assert "total statements=600" in ev[0].summary


def test_collect_delta_summary():
    ev = TableLayoutCheck().collect(_ctx())
    assert "85 of 100" in ev[1].summary
    assert "85.0%" in ev[1].summary


def test_collect_layout_evidence_rows():
    ev = TableLayoutCheck().collect(_ctx())
    row = ev[0].rows[0]
    assert row["optimize_stmts"] == 20
    assert row["zorder_stmts"] == 8
    assert row["cluster_by_stmts"] == 3


def test_judge_maps_llm_verdict_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "OPTIMIZE runs found but no clustering key evidence"}'
    )
    f = TableLayoutCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_no_llm_degrades_to_unassessed():
    f = TableLayoutCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
