from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.co_cost_attribution import OrcCostAttributionCheck

_Q = Question(
    id="ORC-CO-05",
    pillar_id="cost-optimization",
    title="Attribute workflow cost by team/pipeline",
    principle="Monitor and control cost",
)

# FakeSqlClient matches SQL containing "custom_tags" (unique alias in this check's SQL).
def _ctx(total: int, tagged: int) -> AgentContext:
    rows = [{"total": total, "tagged": tagged}]
    return AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient({"custom_tags": rows}),
        catalogs=["main"],
    )


def test_orchestration_co05_met_high_confidence():
    # 90 of 100 workflow rows tagged -> ratio 0.90 >= 0.80 -> MET
    f = OrcCostAttributionCheck().run(_Q, _ctx(100, 90))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.9
    assert f.sources and f.sources[0].kind == "sql"


def test_orchestration_co05_partial():
    # 50 of 100 -> ratio 0.50 -> PARTIAL (>= 0.40)
    f = OrcCostAttributionCheck().run(_Q, _ctx(100, 50))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_orchestration_co05_not_met():
    # 10 of 100 -> ratio 0.10 < 0.40 -> NOT_MET
    f = OrcCostAttributionCheck().run(_Q, _ctx(100, 10))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.HIGH


def test_orchestration_co05_no_usage_unknown_low():
    f = OrcCostAttributionCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
    assert f.sources


def test_orchestration_co05_evidence_summary_contains_counts():
    ev = OrcCostAttributionCheck().collect(
        AgentContext(
            assessment_id="a1",
            layer="orchestration",
            sql=FakeSqlClient({"custom_tags": [{"total": 200, "tagged": 180}]}),
            catalogs=["main"],
        )
    )
    assert "180" in ev[0].summary
    assert "200" in ev[0].summary
