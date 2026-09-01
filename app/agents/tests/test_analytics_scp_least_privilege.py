from __future__ import annotations

from waf_agents.analytics.checks.scp_least_privilege import AnalyticsLeastPrivilegeCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-SCP-02",
    pillar_id="security-compliance-privacy",
    title="Enforce least privilege on analytics data",
    principle="Manage identity and access using least privilege",
)

# Needle: "table_privileges" -> _SQL (FROM system.information_schema.table_privileges)


def _ctx(
    *,
    rows: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient({"table_privileges": rows or []}),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_shows_group_vs_user_grants():
    rows = [{"total_grants": 100, "user_grants": 20, "group_grants": 80}]
    ev = AnalyticsLeastPrivilegeCheck().collect(_ctx(rows=rows))
    assert ev[0].kind == "sql"
    assert "80 of 100" in ev[0].summary
    assert "20 go to individual users" in ev[0].summary


def test_collect_all_user_grants():
    rows = [{"total_grants": 50, "user_grants": 50, "group_grants": 0}]
    ev = AnalyticsLeastPrivilegeCheck().collect(_ctx(rows=rows))
    assert "0 of 50" in ev[0].summary


def test_collect_empty_response_shows_no_grants_message():
    ev = AnalyticsLeastPrivilegeCheck().collect(_ctx(rows=[]))
    assert "No table grants found" in ev[0].summary


def test_collect_evidence_has_grant_rows():
    rows = [{"total_grants": 60, "user_grants": 15, "group_grants": 45}]
    ev = AnalyticsLeastPrivilegeCheck().collect(_ctx(rows=rows))
    assert any(r.get("total_grants") == 60 for r in ev[0].rows)
    assert any(r.get("group_grants") == 45 for r in ev[0].rows)


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Half grants go to individual users"}'
    )
    rows = [{"total_grants": 50, "user_grants": 25, "group_grants": 25}]
    f = AnalyticsLeastPrivilegeCheck().run(_Q, _ctx(rows=rows, llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "All grants to individual users"}'
    )
    rows = [{"total_grants": 30, "user_grants": 30, "group_grants": 0}]
    f = AnalyticsLeastPrivilegeCheck().run(_Q, _ctx(rows=rows, llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_returns_unassessed_with_sources():
    f = AnalyticsLeastPrivilegeCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
