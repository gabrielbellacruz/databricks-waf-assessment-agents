from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.scp_data_protection import DataProtectionCheck

_Q = Question(
    id="PRO-SCP-04",
    pillar_id="security-compliance-privacy",
    title="Protect intermediate/processed data",
    principle="Govern and protect access to intermediate and final processed data",
)

_UC_ROWS = [{"total_tables": 100, "uc_tables": 90}]
_GRANT_ROWS = [{"total_grants": 50, "broad_grants": 2}]

_UC_LOW = [{"total_tables": 100, "uc_tables": 30}]
_GRANT_HIGH = [{"total_grants": 50, "broad_grants": 40}]


def _ctx(
    uc_rows: list[dict] | None = None,
    grant_rows: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient({
            "uc_tables": uc_rows if uc_rows is not None else _UC_ROWS,
            "table_privileges": grant_rows if grant_rows is not None else _GRANT_ROWS,
        }),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_uc_coverage_summary():
    ev = DataProtectionCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "90 of 100" in ev[0].summary
    assert "90.0%" in ev[0].summary


def test_collect_grant_breadth_summary():
    ev = DataProtectionCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "50 total" in ev[1].summary
    assert "2 broad" in ev[1].summary


def test_collect_returns_note_evidence():
    ev = DataProtectionCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[2].kind == "note"
    assert "encryption" in ev[2].summary.lower()


def test_collect_empty_tables_handled():
    ev = DataProtectionCheck().collect(_ctx(uc_rows=[], grant_rows=[]))
    assert "0 of 0" in ev[0].summary


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "High UC coverage and minimal broad grants"}'
    )
    f = DataProtectionCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "Low UC coverage and many broad grants"}'
    )
    f = DataProtectionCheck().run(_Q, _ctx(_UC_LOW, _GRANT_HIGH, llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = DataProtectionCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
