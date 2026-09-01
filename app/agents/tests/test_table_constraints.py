from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.table_constraints import TableConstraintsCheck

_Q = Question(
    id="STO-R-04",
    pillar_id="reliability",
    title="Enforce constraints on stored tables",
    principle="Maintain data integrity",
)


def _ctx(total_tables: int, constrained_tables: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(
            {
                "information_schema.tables": [{"total_tables": total_tables}],
                "table_constraints": [{"constrained_tables": constrained_tables}],
            }
        ),
        catalogs=["main"],
    )


def test_met():
    # 60/100 = 60 % -> MET (threshold >= 50 %)
    f = TableConstraintsCheck().run(_Q, _ctx(100, 60))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.6
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    # 30/100 = 30 % -> PARTIAL (threshold >= 20 %)
    f = TableConstraintsCheck().run(_Q, _ctx(100, 30))
    assert f.verdict is Verdict.PARTIAL


def test_not_met():
    # 10/100 = 10 % -> NOT_MET (< 20 %)
    f = TableConstraintsCheck().run(_Q, _ctx(100, 10))
    assert f.verdict is Verdict.NOT_MET


def test_exactly_at_met_boundary():
    # 50/100 = 50 % is exactly at the MET threshold -> MET
    f = TableConstraintsCheck().run(_Q, _ctx(100, 50))
    assert f.verdict is Verdict.MET
    assert f.score == 0.5


def test_exactly_at_partial_boundary():
    # 20/100 = 20 % is exactly at the PARTIAL threshold -> PARTIAL
    f = TableConstraintsCheck().run(_Q, _ctx(100, 20))
    assert f.verdict is Verdict.PARTIAL


def test_empty_is_unknown_low():
    f = TableConstraintsCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_constrained_capped_at_one():
    # constrained_tables > total_tables should not produce score > 1.0
    f = TableConstraintsCheck().run(_Q, _ctx(10, 15))
    assert f.score == 1.0
    assert f.verdict is Verdict.MET
