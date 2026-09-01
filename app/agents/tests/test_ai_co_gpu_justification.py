from __future__ import annotations

from waf_agents.ai.checks.co_gpu_justification import GpuJustificationCheck
from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-CO-03",
    pillar_id="cost-optimization",
    title="Only use GPUs where they are justified",
    principle="Choose optimal resources",
)

# Distinct SQL needle: "gpu_dbu" (AS gpu_dbu) appears only in _SQL.


def _ctx(total: float, gpu: float) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(
            {"gpu_dbu": [{"total_serving_dbu": total, "gpu_dbu": gpu}]}
        ),
        catalogs=["main"],
    )


def test_met_low_gpu_share():
    # 20% GPU share -> MET
    f = GpuJustificationCheck().run(_Q, _ctx(1000.0, 200.0))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score is not None
    assert abs(f.score - 0.2) < 0.001


def test_partial_medium_gpu_share():
    # 50% GPU share -> PARTIAL
    f = GpuJustificationCheck().run(_Q, _ctx(1000.0, 500.0))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_not_met_high_gpu_share():
    # 90% GPU share -> NOT_MET
    f = GpuJustificationCheck().run(_Q, _ctx(1000.0, 900.0))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.HIGH


def test_boundary_exactly_at_met_threshold():
    # 30% is the exact MET boundary -> MET
    f = GpuJustificationCheck().run(_Q, _ctx(1000.0, 300.0))
    assert f.verdict is Verdict.MET


def test_boundary_just_above_met_threshold():
    # 31% -> PARTIAL
    f = GpuJustificationCheck().run(_Q, _ctx(1000.0, 310.0))
    assert f.verdict is Verdict.PARTIAL


def test_no_serving_usage_is_unknown_low():
    f = GpuJustificationCheck().run(_Q, _ctx(0.0, 0.0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_score_is_gpu_ratio():
    f = GpuJustificationCheck().run(_Q, _ctx(400.0, 100.0))
    # 100/400 = 0.25
    assert f.score is not None
    assert abs(f.score - 0.25) < 0.001


def test_collect_evidence_has_correct_rows():
    check = GpuJustificationCheck()
    ctx = _ctx(800.0, 400.0)
    ev = check.collect(ctx)
    assert len(ev) == 1
    assert ev[0].kind == "sql"
    row = ev[0].rows[0]
    assert row["total_serving_dbu"] == 800.0
    assert row["gpu_dbu"] == 400.0
    assert row["gpu_pct"] == 50.0
