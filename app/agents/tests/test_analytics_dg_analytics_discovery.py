from __future__ import annotations

from waf_agents.analytics.checks.dg_analytics_discovery import AnalyticsDiscoveryCheck
from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-DG-05",
    pillar_id="data-ai-governance",
    title="Enable discovery of analytics assets",
    principle="Analytics consumers should be able to find and evaluate data assets",
)


def _ctx(total: int, described: int, tagged: int = 10) -> AgentContext:
    # Needles: 'trim(comment)' matches _DESCRIBED_SQL,
    #          'tagged_tables' matches _TAGGED_SQL.
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(
            {
                "trim(comment)": [{"total": total, "described": described}],
                "tagged_tables": [{"tagged_tables": tagged}],
            }
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = AnalyticsDiscoveryCheck().run(_Q, _ctx(100, 80))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.80


def test_partial():
    f = AnalyticsDiscoveryCheck().run(_Q, _ctx(100, 50))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_not_met():
    f = AnalyticsDiscoveryCheck().run(_Q, _ctx(100, 20))
    assert f.verdict is Verdict.NOT_MET


def test_empty_is_unknown_low():
    f = AnalyticsDiscoveryCheck().run(_Q, _ctx(0, 0, tagged=0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_two_evidence_sources():
    ev = AnalyticsDiscoveryCheck().collect(
        AgentContext(
            assessment_id="a1",
            layer="analytics",
            sql=FakeSqlClient(
                {
                    "trim(comment)": [{"total": 50, "described": 30}],
                    "tagged_tables": [{"tagged_tables": 7}],
                }
            ),
            catalogs=["main"],
        )
    )
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    assert "30 of 50" in ev[0].summary
    assert ev[1].kind == "sql"
    assert "7" in ev[1].summary
