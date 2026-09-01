from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.declarative_pipelines import DeclarativePipelinesCheck

_Q = Question(
    id="ING-OE-02",
    pillar_id="operational-excellence",
    title="Use a declarative ETL framework for ingestion pipelines",
    principle="Operational excellence",
)


def _ctx(pipelines: int, jobs: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient(
            {
                "system.lakeflow.pipelines": [{"n": pipelines}],
                "system.lakeflow.jobs": [{"n": jobs}],
            }
        ),
        catalogs=["main"],
    )


def test_met_when_ratio_at_half():
    # 5 pipelines, 5 jobs -> ratio = 0.50 -> MET
    f = DeclarativePipelinesCheck().run(_Q, _ctx(5, 5))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.5
    assert len(f.sources) == 2
    assert f.sources[0].kind == "sql"
    assert f.sources[1].kind == "sql"


def test_met_all_pipelines():
    # 10 pipelines, 0 jobs -> ratio = 1.0 -> MET
    f = DeclarativePipelinesCheck().run(_Q, _ctx(10, 0))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 1.0


def test_partial():
    # 3 pipelines, 10 jobs -> ratio ≈ 0.231 (>= 0.20 but < 0.50) -> PARTIAL
    f = DeclarativePipelinesCheck().run(_Q, _ctx(3, 10))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_not_met_no_pipelines():
    # 0 pipelines, 10 jobs -> ratio = 0.0 -> NOT_MET
    f = DeclarativePipelinesCheck().run(_Q, _ctx(0, 10))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_both_empty_is_unknown_low():
    f = DeclarativePipelinesCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
