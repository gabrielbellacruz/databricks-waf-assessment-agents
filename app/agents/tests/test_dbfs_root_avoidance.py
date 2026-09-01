from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.dbfs_root_avoidance import DbfsRootAvoidanceCheck

_Q = Question(
    id="STO-SCP-03",
    pillar_id="security-compliance-privacy",
    title="Avoid storing production data in DBFS root",
    principle="Secure data storage",
)


def _ctx(total_located: int, on_dbfs_root: int, hive_tables: int = 0) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(
            {
                "storage_path IS NOT NULL": [
                    {"total_located": total_located, "on_dbfs_root": on_dbfs_root}
                ],
                "table_catalog = 'hive_metastore'": [{"hive_tables": hive_tables}],
            }
        ),
        catalogs=["main"],
    )


def test_met_very_few_on_dbfs():
    # 3/100 = 3 % on DBFS root -> MET (threshold <= 5 %)
    f = DbfsRootAvoidanceCheck().run(_Q, _ctx(100, 3))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == round(1.0 - 3 / 100, 4)
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    # 10/100 = 10 % -> PARTIAL (threshold <= 20 %)
    f = DbfsRootAvoidanceCheck().run(_Q, _ctx(100, 10))
    assert f.verdict is Verdict.PARTIAL


def test_not_met():
    # 50/100 = 50 % on DBFS root -> NOT_MET
    f = DbfsRootAvoidanceCheck().run(_Q, _ctx(100, 50))
    assert f.verdict is Verdict.NOT_MET


def test_exactly_at_met_boundary():
    # 5/100 = 5 % is exactly at the MET threshold -> MET
    f = DbfsRootAvoidanceCheck().run(_Q, _ctx(100, 5))
    assert f.verdict is Verdict.MET
    assert f.score == round(1.0 - 5 / 100, 4)


def test_exactly_at_partial_boundary():
    # 20/100 = 20 % is exactly at the PARTIAL threshold -> PARTIAL
    f = DbfsRootAvoidanceCheck().run(_Q, _ctx(100, 20))
    assert f.verdict is Verdict.PARTIAL


def test_zero_located_is_unknown_low():
    f = DbfsRootAvoidanceCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_hive_tables_appear_in_rationale():
    f = DbfsRootAvoidanceCheck().run(_Q, _ctx(100, 3, hive_tables=25))
    assert "25" in f.rationale
    assert f.verdict is Verdict.MET
