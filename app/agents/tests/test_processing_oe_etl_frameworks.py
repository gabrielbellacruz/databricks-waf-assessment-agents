from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.oe_etl_frameworks import EtlFrameworksCheck

_Q = Question(
    id="PRO-OE-01",
    pillar_id="operational-excellence",
    title="Use ETL frameworks for transformation pipelines",
    principle="Prefer managed ETL frameworks over ad-hoc jobs",
)


def _ctx(pipelines: int, jobs: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient({
            "lakeflow.pipelines": [{"n": pipelines}],
            "lakeflow.jobs": [{"n": jobs}],
        }),
        catalogs=["main"],
    )


def test_met_majority_pipelines():
    # 6 pipelines, 4 jobs -> 60% -> MET (>= 0.50)
    f = EtlFrameworksCheck().run(_Q, _ctx(6, 4))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score is not None
    assert abs(f.score - 0.6) < 0.001


def test_partial():
    # 3 pipelines, 12 jobs -> 20% -> PARTIAL (>= 0.20, < 0.50)
    f = EtlFrameworksCheck().run(_Q, _ctx(3, 12))
    assert f.verdict is Verdict.PARTIAL
    assert f.score is not None


def test_not_met_low_ratio():
    # 1 pipeline, 19 jobs -> 5% -> NOT_MET
    f = EtlFrameworksCheck().run(_Q, _ctx(1, 19))
    assert f.verdict is Verdict.NOT_MET


def test_empty_is_unknown_low():
    f = EtlFrameworksCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_only_pipelines_is_met():
    # 10 pipelines, 0 jobs -> 100% -> MET
    f = EtlFrameworksCheck().run(_Q, _ctx(10, 0))
    assert f.verdict is Verdict.MET
    assert f.score == 1.0


def test_collect_returns_two_evidence_items():
    ev = EtlFrameworksCheck().collect(_ctx(5, 5))
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert "pipeline" in ev[0].summary.lower()
    assert "job" in ev[1].summary.lower()
