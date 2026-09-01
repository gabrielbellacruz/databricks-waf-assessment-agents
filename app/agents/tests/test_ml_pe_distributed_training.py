from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Question, Verdict
from waf_agents.ml.checks.pe_distributed_training import MlDistributedTrainingCheck

_Q = Question(
    id="ML-PE-02",
    pillar_id="performance-efficiency",
    title="Use distributed training where beneficial",
    principle="Design workloads for performance",
)

_CLUSTER_ROWS = [{"total_clusters": 8, "large_clusters": 3, "max_workers_seen": 16}]
_JOB_ROWS = [{"total_runs": 40, "long_runs": 12}]


def _ctx(*, cluster_rows=None, job_rows=None, llm_response: str | None = "") -> AgentContext:
    responses = {
        "max_autoscale_workers": cluster_rows if cluster_rows is not None else _CLUSTER_ROWS,
        "long_runs": job_rows if job_rows is not None else _JOB_ROWS,
    }
    return AgentContext(
        assessment_id="test-ml-pe02",
        layer="ml",
        sql=FakeSqlClient(responses),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_large_cluster_summary():
    ev = MlDistributedTrainingCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "3 of 8" in ev[0].summary
    assert "max workers seen: 16" in ev[0].summary


def test_collect_long_run_summary():
    ev = MlDistributedTrainingCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "12 of 40" in ev[1].summary
    assert "30.0%" in ev[1].summary  # 12/40


def test_collect_no_clusters_returns_empty_summary():
    ev = MlDistributedTrainingCheck().collect(_ctx(cluster_rows=[]))
    assert "No active clusters" in ev[0].summary


def test_collect_attaches_limitation_note():
    ev = MlDistributedTrainingCheck().collect(_ctx())
    assert ev[2].kind == "note"
    assert "Horovod" in ev[2].summary


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "low", "score": null,'
        ' "rationale": "Large clusters present"}'
    )
    f = MlDistributedTrainingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL


def test_no_llm_degrades_to_unassessed():
    f = MlDistributedTrainingCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
