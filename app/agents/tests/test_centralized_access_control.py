from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.centralized_access_control import CentralizedAccessControlCheck

_Q = Question(
    id="STO-DG-03",
    pillar_id="data-ai-governance",
    title="Centralize access control on stored data",
    principle="Enforce least-privilege access through Unity Catalog centralized grants",
)

# Needles are distinct, non-overlapping substrings of the three SQL strings:
#   "total_grants"   -> _GRANT_SUMMARY_SQL   (AS total_grants)
#   "uc_table_count" -> _UC_TABLE_COUNT_SQL  (AS uc_table_count)
#   "grant_count"    -> _TOP_GRANTEES_SQL    (AS grant_count)
_FAKE_RESPONSES = {
    "total_grants": [{"total_grants": 150, "distinct_grantees": 12, "broad_grants": 5}],
    "uc_table_count": [{"uc_table_count": 250}],
    "grant_count": [
        {"grantee": "data_eng_grp", "grant_count": 80},
        {"grantee": "account users", "grant_count": 5},
        {"grantee": "analysts_grp", "grant_count": 65},
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# --- collect() tests ---

def test_collect_grant_summary():
    ev = CentralizedAccessControlCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "150 total table grants" in ev[0].summary
    assert "12 distinct grantees" in ev[0].summary
    assert "5 broad/public grants" in ev[0].summary


def test_collect_broad_grant_percentage():
    ev = CentralizedAccessControlCheck().collect(_ctx())
    # 5 / 150 = 3.3%
    assert "3.3%" in ev[0].summary


def test_collect_uc_table_coverage():
    ev = CentralizedAccessControlCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "250 managed/external tables" in ev[1].summary


def test_collect_grantee_detail():
    ev = CentralizedAccessControlCheck().collect(_ctx())
    assert ev[2].kind == "sql"
    assert len(ev[2].rows) == 3
    assert any(r.get("grantee") == "account users" for r in ev[2].rows)


def test_collect_returns_three_evidence_items():
    ev = CentralizedAccessControlCheck().collect(_ctx())
    assert len(ev) == 3


# --- judge() tests ---

def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some broad grants exist; most are scoped to groups"}'
    )
    f = CentralizedAccessControlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even when it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "Majority of grants are to account users"}'
    )
    f = CentralizedAccessControlCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = CentralizedAccessControlCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
