from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.co_cluster_reuse import OrcClusterReuseCheck

_Q = Question(
    id="ORC-CO-02",
    pillar_id="cost-optimization",
    title="Share clusters across tasks to reduce cost",
    principle="Optimize cost",
)

# FakeSqlClient matches SQL containing "sharing_jobs" (unique alias in this check's SQL).
def _ctx(total: int, sharing: int) -> AgentContext:
    rows = [{"total_multi_task_jobs": total, "sharing_jobs": sharing}]
    return AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient({"sharing_jobs": rows}),
        catalogs=["main"],
    )


def test_orchestration_co02_met_medium_confidence():
    # 8 of 10 multi-task jobs share clusters -> ratio 0.80 >= 0.70 -> MET
    f = OrcClusterReuseCheck().run(_Q, _ctx(10, 8))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.8
    assert f.sources and f.sources[0].kind == "sql"


def test_orchestration_co02_partial():
    # 5 of 10 -> ratio 0.50 -> PARTIAL (>= 0.40)
    f = OrcClusterReuseCheck().run(_Q, _ctx(10, 5))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_orchestration_co02_not_met():
    # 2 of 10 -> ratio 0.20 < 0.40 -> NOT_MET
    f = OrcClusterReuseCheck().run(_Q, _ctx(10, 2))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_orchestration_co02_no_jobs_unknown_low():
    f = OrcClusterReuseCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
    assert f.sources


def test_orchestration_co02_evidence_summary_contains_counts():
    ev = OrcClusterReuseCheck().collect(
        AgentContext(
            assessment_id="a1",
            layer="orchestration",
            sql=FakeSqlClient({"sharing_jobs": [{"total_multi_task_jobs": 7, "sharing_jobs": 3}]}),
            catalogs=["main"],
        )
    )
    assert "3" in ev[0].summary
    assert "7" in ev[0].summary
