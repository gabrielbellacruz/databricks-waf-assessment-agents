from __future__ import annotations

from waf_agents.analytics.checks.iu_self_service_governance import SelfServiceGovernanceCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-IU-03",
    pillar_id="interoperability-usability",
    title="Provide self-service analytics with governance",
    principle="Business users should self-serve data with appropriate guardrails",
)

# Needles: 'running_warehouses' matches _WAREHOUSE_SQL (also has 'total_warehouses'
#           but 'running_warehouses' is more specific to that SQL),
#          'broad_grants' matches _GRANT_ANALYSIS_SQL,
#          'uc_tables' matches _UC_COVERAGE_SQL.
_FAKE_RESPONSES = {
    "running_warehouses": [{"total_warehouses": 4, "running_warehouses": 2}],
    "broad_grants": [
        {"total_grants": 200, "distinct_grantees": 30, "broad_grants": 10}
    ],
    "uc_tables": [{"uc_tables": 500}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_warehouse_evidence():
    ev = SelfServiceGovernanceCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "4" in ev[0].summary
    assert "warehouse" in ev[0].summary.lower()


def test_collect_grant_evidence():
    ev = SelfServiceGovernanceCheck().collect(_ctx())
    assert "200" in ev[1].summary
    assert "30" in ev[1].summary
    assert "10" in ev[1].summary


def test_collect_uc_coverage_evidence():
    ev = SelfServiceGovernanceCheck().collect(_ctx())
    assert len(ev) == 3
    assert "500" in ev[2].summary


def test_judge_met():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Warehouses with governed UC access"}'
    )
    f = SelfServiceGovernanceCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "No warehouses or no UC governance"}'
    )
    f = SelfServiceGovernanceCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = SelfServiceGovernanceCheck().run(_Q, _ctx(llm_response=None))
    assert f.auto_assessable is False
    assert f.sources
