from __future__ import annotations

from waf_agents.analytics.checks.dg_row_column_security import RowColumnSecurityCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-DG-03",
    pillar_id="data-ai-governance",
    title="Apply row/column-level security to analytics",
    principle="Sensitive analytics data must be filtered or masked per user identity",
)

# Needles: 'user_grants' matches _PRIVILEGE_SUMMARY_SQL,
#          'masked_columns' matches _COLUMN_MASKS_SQL.
_FAKE_RESPONSES = {
    "user_grants": [
        {"total_grants": 80, "user_grants": 20, "group_grants": 60, "broad_grants": 5}
    ],
    "masked_columns": [{"masked_columns": 4, "masked_tables": 2}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_privilege_evidence():
    ev = RowColumnSecurityCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "80" in ev[0].summary
    assert "60" in ev[0].summary  # group grants


def test_collect_column_mask_evidence():
    ev = RowColumnSecurityCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "4" in ev[1].summary
    assert "mask" in ev[1].summary.lower()


def test_collect_limitation_evidence():
    ev = RowColumnSecurityCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[2].kind == "uc_metadata"
    assert "row" in ev[2].summary.lower()


def test_judge_not_met():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "No row filters or column masks configured"}'
    )
    f = RowColumnSecurityCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_partial():
    resp = (
        '{"verdict": "partial", "confidence": "low",'
        ' "score": null, "rationale": "Some column masks exist but no row filters"}'
    )
    f = RowColumnSecurityCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL


def test_no_llm_degrades_to_unassessed():
    f = RowColumnSecurityCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
