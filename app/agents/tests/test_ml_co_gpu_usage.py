from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.co_gpu_usage import GpuUsageCheck

_Q = Question(
    id="ML-CO-01",
    pillar_id="cost-optimization",
    title="Only use GPUs for workloads that need them",
    principle="Optimise compute spend",
)

# Needle is a unique substring of the SQL for FakeSqlClient matching.
# "all_purpose_gpu_dbus" is unique to this check's SQL alias.
_SQL_NEEDLE = "all_purpose_gpu_dbus"


def _ctx(
    *,
    total: float = 0.0,
    gpu: float = 0.0,
    ap_gpu: float = 0.0,
    job_gpu: float = 0.0,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(
            {
                _SQL_NEEDLE: [
                    {
                        "total_compute_dbus": total,
                        "gpu_dbus": gpu,
                        "all_purpose_gpu_dbus": ap_gpu,
                        "job_gpu_dbus": job_gpu,
                    }
                ]
            }
        ),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# --- collect() tests ----------------------------------------------------------


def test_collect_returns_two_evidence_pieces():
    ev = GpuUsageCheck().collect(_ctx(total=100.0, gpu=30.0, ap_gpu=10.0, job_gpu=20.0))
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    assert ev[1].kind == "note"


def test_collect_sql_evidence_has_rows():
    ev = GpuUsageCheck().collect(_ctx(total=100.0, gpu=30.0, ap_gpu=10.0, job_gpu=20.0))
    row = ev[0].rows[0]
    assert row["total_compute_dbus"] == 100.0
    assert row["gpu_dbus"] == 30.0
    assert row["all_purpose_gpu_dbus"] == 10.0
    assert row["job_gpu_dbus"] == 20.0


def test_collect_no_gpu_usage_summary():
    ev = GpuUsageCheck().collect(_ctx(total=100.0, gpu=0.0, ap_gpu=0.0, job_gpu=0.0))
    assert "No GPU compute DBUs" in ev[0].summary


def test_collect_no_compute_usage_summary():
    ev = GpuUsageCheck().collect(_ctx())
    assert "No compute billing usage" in ev[0].summary


def test_collect_shows_percentages_when_gpu_present():
    ev = GpuUsageCheck().collect(_ctx(total=100.0, gpu=40.0, ap_gpu=30.0, job_gpu=10.0))
    # 40/100 = 40%, 30/40 = 75% all-purpose, 10/40 = 25% job
    assert "40%" in ev[0].summary
    assert "75%" in ev[0].summary


# --- judge() tests (LLM path) ------------------------------------------------


def test_judge_maps_llm_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "GPU is used only for training jobs"}'
    )
    f = GpuUsageCheck().run(
        _Q, _ctx(total=100.0, gpu=20.0, ap_gpu=2.0, job_gpu=18.0, llm_response=resp)
    )
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_maps_llm_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "Most GPU DBUs are on all-purpose clusters"}'
    )
    f = GpuUsageCheck().run(
        _Q, _ctx(total=100.0, gpu=80.0, ap_gpu=70.0, job_gpu=10.0, llm_response=resp)
    )
    assert f.verdict is Verdict.NOT_MET


def test_judge_caps_llm_confidence_at_medium():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some GPUs used appropriately"}'
    )
    f = GpuUsageCheck().run(
        _Q, _ctx(total=100.0, gpu=50.0, ap_gpu=25.0, job_gpu=25.0, llm_response=resp)
    )
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = GpuUsageCheck().run(_Q, _ctx(total=100.0, gpu=30.0, llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
