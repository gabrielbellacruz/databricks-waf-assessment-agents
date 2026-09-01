from __future__ import annotations

from waf_agents.analytics.checks.r_production_serving import ProductionServingCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-R-02",
    pillar_id="reliability",
    title="Use managed, production-grade serving for analytics",
    principle="Ensure analytics serving is reliable and stable",
)

# Needles that uniquely identify each SQL:
#   "channel_name"  -> _WAREHOUSES_SQL  (GROUP BY ... channel_name ...)
#   "event_type"    -> _EVENTS_SQL      (GROUP BY event_type)
_FAKE_RESPONSES = {
    "channel_name": [
        {"warehouse_type": "PRO", "channel_name": "CHANNEL_NAME_CURRENT",
         "auto_stop_mins": 30, "min_num_clusters": 1, "max_num_clusters": 3, "cnt": 2},
        {"warehouse_type": "CLASSIC", "channel_name": "CHANNEL_NAME_PREVIEW",
         "auto_stop_mins": 10, "min_num_clusters": 1, "max_num_clusters": 1, "cnt": 1},
    ],
    "event_type": [
        {"event_type": "RUNNING", "cnt": 42},
        {"event_type": "STOPPED", "cnt": 5},
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
    ev = ProductionServingCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert ev[2].kind == "note"


def test_collect_warehouse_summary_counts_types():
    ev = ProductionServingCheck().collect(_ctx())
    # 3 total (2 PRO + 1 CLASSIC), 2 PRO/SERVERLESS, 1 preview
    assert "3 SQL warehouse(s)" in ev[0].summary
    assert "2 PRO/SERVERLESS" in ev[0].summary
    assert "1 on CHANNEL_NAME_PREVIEW" in ev[0].summary


def test_collect_event_summary():
    ev = ProductionServingCheck().collect(_ctx())
    assert "RUNNING=42" in ev[1].summary


def test_judge_maps_llm_verdict_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some warehouses on preview channel"}'
    )
    f = ProductionServingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "All warehouses on stable channel"}'
    )
    f = ProductionServingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET


def test_no_llm_degrades_to_unassessed():
    f = ProductionServingCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
