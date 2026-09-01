from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.scp_credential_management import OrcCredentialManagementCheck

_Q = Question(
    id="ORC-SCP-03",
    pillar_id="scp",
    title="Manage workflow tokens and credentials securely",
    principle="Store workflow tokens and credentials in a secret manager rather than inline",
)

_SQL_NEEDLE = "system.query.history"


def _ctx(
    secret_refs: int,
    hardcoded: int,
    total: int,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient(
            {
                _SQL_NEEDLE: [
                    {
                        "secret_ref_stmts": secret_refs,
                        "possible_hardcoded": hardcoded,
                        "total_stmts": total,
                    }
                ]
            }
        ),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_secret_refs_in_summary():
    ev = OrcCredentialManagementCheck().collect(_ctx(20, 3, 500))
    assert ev[0].kind == "sql"
    assert "secret_ref_stmts" in ev[0].summary or "Secret-manager references" in ev[0].summary


def test_collect_hardcoded_count_in_summary():
    ev = OrcCredentialManagementCheck().collect(_ctx(20, 3, 500))
    assert "3" in ev[0].summary  # possible_hardcoded count


def test_collect_includes_note():
    ev = OrcCredentialManagementCheck().collect(_ctx(10, 2, 100))
    assert len(ev) == 2
    assert ev[1].kind == "note"


def test_collect_no_history_rows():
    ctx = AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient(),  # empty responses → collect returns empty list
        llm=FakeLlmClient(""),
    )
    ev = OrcCredentialManagementCheck().collect(ctx)
    assert "No query-history rows" in ev[0].summary


def test_collect_evidence_rows():
    ev = OrcCredentialManagementCheck().collect(_ctx(15, 4, 300))
    row = ev[0].rows[0]
    assert row["secret_ref_stmts"] == 15
    assert row["possible_hardcoded"] == 4
    assert row["total_stmts"] == 300


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "High secret() usage, no hardcoded credentials found"}'
    )
    f = OrcCredentialManagementCheck().run(_Q, _ctx(50, 0, 200, llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "Multiple password= patterns found"}'
    )
    f = OrcCredentialManagementCheck().run(_Q, _ctx(0, 10, 200, llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = OrcCredentialManagementCheck().run(_Q, _ctx(5, 2, 100, llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
