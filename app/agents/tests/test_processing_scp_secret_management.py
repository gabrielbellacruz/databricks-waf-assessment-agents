from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.scp_secret_management import SecretManagementCheck

_Q = Question(
    id="PRO-SCP-03",
    pillar_id="security-compliance-privacy",
    title="Keep secrets out of transformation code",
    principle="Use secret scopes rather than hard-coded credentials in transformations",
)

_GOOD_ROWS = [
    {"secret_ref_stmts": 15, "possible_hardcoded": 0, "total_stmts": 200}
]
_RISK_ROWS = [
    {"secret_ref_stmts": 0, "possible_hardcoded": 5, "total_stmts": 100}
]


def _ctx(rows: list[dict], llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient({"query.history": rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_shows_secret_refs():
    ev = SecretManagementCheck().collect(_ctx(_GOOD_ROWS))
    assert ev[0].kind == "sql"
    # Summary format: "Secret-manager references (secret()/dbutils.secrets)=15 (good); ..."
    assert "=15" in ev[0].summary
    assert "patterns=0" in ev[0].summary


def test_collect_shows_risk_patterns():
    ev = SecretManagementCheck().collect(_ctx(_RISK_ROWS))
    assert "patterns=5" in ev[0].summary


def test_collect_no_rows_fallback():
    ev = SecretManagementCheck().collect(_ctx([]))
    assert "No query-history rows" in ev[0].summary
    assert ev[0].rows == []


def test_collect_returns_note_evidence():
    ev = SecretManagementCheck().collect(_ctx(_GOOD_ROWS))
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "false positives" in ev[1].summary.lower() or "Manual confirmation" in ev[1].summary


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Secret-manager usage is high; no hard-coded patterns"}'
    )
    f = SecretManagementCheck().run(_Q, _ctx(_GOOD_ROWS, llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "Hard-coded credential patterns detected"}'
    )
    f = SecretManagementCheck().run(_Q, _ctx(_RISK_ROWS, llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = SecretManagementCheck().run(_Q, _ctx(_GOOD_ROWS, llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
