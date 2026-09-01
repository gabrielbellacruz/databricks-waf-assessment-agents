from __future__ import annotations

from waf_agents.analytics.checks.r_data_consistency import DataConsistencyCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-R-03",
    pillar_id="reliability",
    title="Ensure consistency of served analytics data",
    principle="Ensure dashboards reflect a coherent, up-to-date snapshot",
)

# Needles:
#   "refresh_mv_stmts"  -> _MV_REFRESH_SQL
#   "delta_tables"      -> _DELTA_SQL  (AS delta_tables)
_FAKE_RESPONSES = {
    "refresh_mv_stmts": [
        {"refresh_mv_stmts": 15, "create_mv_stmts": 3, "total_stmts": 500}
    ],
    "delta_tables": [
        {"total_tables": 80, "delta_tables": 72}
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
    ev = DataConsistencyCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert ev[2].kind == "note"


def test_collect_mv_summary_contains_counts():
    ev = DataConsistencyCheck().collect(_ctx())
    assert "REFRESH=15" in ev[0].summary
    assert "CREATE=3" in ev[0].summary
    assert "total statements=500" in ev[0].summary


def test_collect_delta_summary_contains_percentage():
    ev = DataConsistencyCheck().collect(_ctx())
    # 72/80 = 90.0%
    assert "72 of 80" in ev[1].summary
    assert "90.0%" in ev[1].summary


def test_collect_delta_evidence_rows():
    ev = DataConsistencyCheck().collect(_ctx())
    assert ev[1].rows[0]["total_tables"] == 80
    assert ev[1].rows[0]["delta_tables"] == 72


def test_judge_maps_llm_verdict_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some MVs refreshed but not all"}'
    )
    f = DataConsistencyCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_no_llm_degrades_to_unassessed():
    f = DataConsistencyCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
