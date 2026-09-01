from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.pe_prewarming import OrcPrewarmingCheck

_Q = Question(
    id="ORC-PE-03",
    pillar_id="performance-efficiency",
    title="Account for compute prewarming in schedules",
    principle="Optimize performance through efficient resource scheduling",
)

# Distinct needles:
#   "autoscaling_clusters" → _SQL_CLUSTERS
#   "avg_run_seconds"      → _SQL_RUNS (has AND period_end_time IS NOT NULL)
_FAKE = {
    "autoscaling_clusters": [{"total_active_clusters": 12, "autoscaling_clusters": 5}],
    "avg_run_seconds": [{"total_runs": 100, "avg_run_seconds": 420.0}],
}

_LLM_MET = (
    '{"verdict": "met", "confidence": "low", "score": null,'
    ' "rationale": "Cluster setup visible; prewarming cannot be confirmed from system tables."}'
)
_LLM_UNKNOWN = (
    '{"verdict": "unknown", "confidence": "low", "score": null,'
    ' "rationale": "Insufficient evidence to assess prewarming configuration."}'
)


def _ctx(
    *,
    llm_response: str | None = _LLM_MET,
    fake: dict | None = None,
) -> AgentContext:
    return AgentContext(
        assessment_id="test-orc",
        layer="orchestration",
        sql=FakeSqlClient(fake if fake is not None else dict(_FAKE)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# --- collect() ---

def test_collect_returns_three_evidence_entries():
    ev = OrcPrewarmingCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_cluster_evidence_content():
    ev = OrcPrewarmingCheck().collect(_ctx())
    ev_clusters = ev[0]
    assert ev_clusters.kind == "sql"
    assert "12" in ev_clusters.summary
    assert ev_clusters.rows[0]["total_active_clusters"] == 12
    assert ev_clusters.rows[0]["autoscaling_clusters"] == 5


def test_collect_run_duration_evidence_content():
    ev = OrcPrewarmingCheck().collect(_ctx())
    ev_runs = ev[1]
    assert ev_runs.kind == "sql"
    assert "100" in ev_runs.summary
    assert ev_runs.rows[0]["avg_run_seconds"] == 420.0


def test_collect_note_mentions_pools_and_limitation():
    ev = OrcPrewarmingCheck().collect(_ctx())
    note = ev[2]
    assert note.kind == "note"
    assert "pool" in note.summary.lower() or "prewarm" in note.summary.lower()


def test_collect_empty_sql_result_handled():
    ctx = AgentContext(
        assessment_id="t",
        layer="orchestration",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = OrcPrewarmingCheck().collect(ctx)
    assert ev[0].rows[0]["total_active_clusters"] == 0
    assert ev[1].rows[0]["total_runs"] == 0


# --- judge() ---

def test_judge_met_verdict():
    f = OrcPrewarmingCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET


def test_judge_unknown_verdict():
    f = OrcPrewarmingCheck().run(_Q, _ctx(llm_response=_LLM_UNKNOWN))
    assert f.verdict is Verdict.UNKNOWN


def test_judge_confidence_capped_at_medium():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "Some prewarming evidence found."}'
    )
    f = OrcPrewarmingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_two_sql_and_note():
    f = OrcPrewarmingCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert kinds.count("sql") == 2
    assert "note" in kinds


# --- llm=None ---

def test_no_llm_degrades_to_unassessed():
    f = OrcPrewarmingCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
