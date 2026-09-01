from __future__ import annotations

from waf_agents.ai.checks.dg_access_control import AiAccessControlCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-DG-03",
    pillar_id="dg",
    title="Control access to models, endpoints, and knowledge bases",
    principle="Restrict AI assets to authorised principals using least-privilege grants",
)

# Distinct needles:
#   "routine_privileges"  -> _ROUTINE_PRIVS_SQL (table name in FROM clause)
#   "guardrail_triggered" -> _GATEWAY_SQL (column alias)
_FAKE = {
    "routine_privileges": [{"routine_grants": 20, "user_grants": 3, "group_grants": 17}],
    "guardrail_triggered": [{"gateway_governed_total": 100, "guardrail_triggered": 12}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_reports_routine_grants():
    ev = AiAccessControlCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "17" in ev[0].summary   # group_grants
    assert "20" in ev[0].summary   # total


def test_collect_reports_gateway_guardrails():
    ev = AiAccessControlCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "100" in ev[1].summary
    assert "12" in ev[1].summary


def test_collect_includes_acl_limitation():
    ev = AiAccessControlCheck().collect(_ctx())
    assert ev[2].kind == "uc_metadata"
    assert "acl" in ev[2].summary.lower() or "permission" in ev[2].summary.lower()


def test_collect_has_three_evidence_items():
    ev = AiAccessControlCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_rows_attached():
    ev = AiAccessControlCheck().collect(_ctx())
    assert ev[0].rows[0]["routine_grants"] == 20
    assert ev[1].rows[0]["guardrail_triggered"] == 12


def test_collect_empty_sql_returns_zeros():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=FakeLlmClient(""),
    )
    ev = AiAccessControlCheck().collect(ctx)
    assert "0" in ev[0].summary


def test_judge_maps_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Some group grants but endpoint ACLs unverified"}'
    )
    f = AiAccessControlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_high_to_medium():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "All grants to groups"}'
    )
    f = AiAccessControlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = AiAccessControlCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
