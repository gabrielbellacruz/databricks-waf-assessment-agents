from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.co_compute_policies import OrcComputePoliciesCheck

_Q = Question(
    id="ORC-CO-04",
    pillar_id="cost-optimization",
    title="Use compute policies to bound workflow cost",
    principle="Optimize cost",
)

# FakeSqlClient matches SQL containing "policy_bound" (unique alias in this check's SQL).
def _ctx(total: int, policy_bound: int) -> AgentContext:
    rows = [{"total_job_clusters": total, "policy_bound": policy_bound}]
    return AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient({"policy_bound": rows}),
        catalogs=["main"],
    )


def test_orchestration_co04_met_high_confidence():
    # 8 of 10 job clusters have a policy -> ratio 0.80 >= 0.70 -> MET
    f = OrcComputePoliciesCheck().run(_Q, _ctx(10, 8))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.8
    assert f.sources and f.sources[0].kind == "sql"


def test_orchestration_co04_partial():
    # 5 of 10 -> ratio 0.50 -> PARTIAL (>= 0.40)
    f = OrcComputePoliciesCheck().run(_Q, _ctx(10, 5))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_orchestration_co04_not_met():
    # 2 of 10 -> ratio 0.20 < 0.40 -> NOT_MET
    f = OrcComputePoliciesCheck().run(_Q, _ctx(10, 2))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.HIGH


def test_orchestration_co04_no_clusters_unknown_low():
    f = OrcComputePoliciesCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
    assert f.sources


def test_orchestration_co04_evidence_summary_contains_counts():
    ev = OrcComputePoliciesCheck().collect(
        AgentContext(
            assessment_id="a1",
            layer="orchestration",
            sql=FakeSqlClient({"policy_bound": [{"total_job_clusters": 15, "policy_bound": 6}]}),
            catalogs=["main"],
        )
    )
    assert "6" in ev[0].summary
    assert "15" in ev[0].summary
