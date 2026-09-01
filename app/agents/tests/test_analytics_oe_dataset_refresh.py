from __future__ import annotations

from waf_agents.analytics.checks.oe_dataset_refresh import DatasetRefreshCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-OE-03",
    pillar_id="operational-excellence",
    title="Automate refresh of analytics datasets",
    principle="Automate deployments and workloads",
)

# Needle: "trigger_type" -> _SQL (GROUP BY trigger_type)


def _ctx(
    *,
    rows: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient({"trigger_type": rows or []}),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_shows_scheduled_ratio():
    rows = [
        {"trigger_type": "SCHEDULED", "run_count": 80},
        {"trigger_type": "MANUAL", "run_count": 20},
    ]
    ev = DatasetRefreshCheck().collect(_ctx(rows=rows))
    assert ev[0].kind == "sql"
    assert "80 of 100" in ev[0].summary
    assert "80.0%" in ev[0].summary


def test_collect_all_manual_shows_zero_automated():
    rows = [{"trigger_type": "MANUAL", "run_count": 50}]
    ev = DatasetRefreshCheck().collect(_ctx(rows=rows))
    assert "0 of 50" in ev[0].summary


def test_collect_file_arrival_counted_as_automated():
    rows = [{"trigger_type": "FILE_ARRIVAL", "run_count": 30}]
    ev = DatasetRefreshCheck().collect(_ctx(rows=rows))
    assert "30 of 30" in ev[0].summary


def test_collect_empty_rows_shows_no_runs_message():
    ev = DatasetRefreshCheck().collect(_ctx(rows=[]))
    assert "No job runs found" in ev[0].summary


def test_collect_includes_note_evidence():
    ev = DatasetRefreshCheck().collect(_ctx(rows=[]))
    kinds = [e.kind for e in ev]
    assert "note" in kinds


def test_judge_maps_llm_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "low",'
        ' "score": null, "rationale": "Mix of scheduled and manual runs"}'
    )
    rows = [
        {"trigger_type": "SCHEDULED", "run_count": 50},
        {"trigger_type": "MANUAL", "run_count": 50},
    ]
    f = DatasetRefreshCheck().run(_Q, _ctx(rows=rows, llm_response=resp))
    assert f.verdict is Verdict.PARTIAL


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "All runs are scheduled"}'
    )
    rows = [{"trigger_type": "SCHEDULED", "run_count": 100}]
    f = DatasetRefreshCheck().run(_Q, _ctx(rows=rows, llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_returns_unassessed_with_sources():
    f = DatasetRefreshCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
