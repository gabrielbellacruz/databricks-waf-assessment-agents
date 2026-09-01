from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.medallion_architecture import MedallionArchitectureCheck

_Q = Question(
    id="STO-OE-04",
    pillar_id="operational-excellence",
    title="Use a layered (medallion) storage architecture",
    principle="Organise storage into bronze / silver / gold layers",
)


def _ctx(total: int, bronze: int, silver: int, gold: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(
            {
                "information_schema.schemata": [
                    {
                        "total_schemas": total,
                        "bronze_count": bronze,
                        "silver_count": silver,
                        "gold_count": gold,
                    }
                ]
            }
        ),
        catalogs=["main"],
    )


def test_met_all_three_layers():
    f = MedallionArchitectureCheck().run(_Q, _ctx(30, 5, 8, 4))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == round(3 / 3, 4)
    assert f.sources and f.sources[0].kind == "sql"


def test_partial_two_layers():
    f = MedallionArchitectureCheck().run(_Q, _ctx(20, 3, 4, 0))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.score == round(2 / 3, 4)


def test_partial_one_layer():
    f = MedallionArchitectureCheck().run(_Q, _ctx(10, 0, 0, 2))
    assert f.verdict is Verdict.PARTIAL
    assert f.score == round(1 / 3, 4)


def test_not_met_no_layers():
    f = MedallionArchitectureCheck().run(_Q, _ctx(10, 0, 0, 0))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.0


def test_empty_is_unknown_low():
    f = MedallionArchitectureCheck().run(_Q, _ctx(0, 0, 0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
