from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.secret_management import SecretManagementCheck

_Q = Question(
    id="ING-SCP-01",
    pillar_id="security-compliance-privacy",
    title="Store source-system credentials with secret management",
    principle="Protect data in transit and at rest",
)

# Values are strings to match what a real SqlClient returns from the wire.
_ROWS = [{"secret_ref_stmts": "12", "possible_hardcoded": "3", "total_stmts": "500"}]


def _ctx(*, sql_rows: list[dict] | None = None, llm_response: str | None = "") -> AgentContext:
    rows = sql_rows if sql_rows is not None else _ROWS
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient({"system.query.history": rows}),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_produces_sql_and_note_evidence():
    evidence = SecretManagementCheck().collect(_ctx())
    assert len(evidence) == 2
    assert [e.kind for e in evidence] == ["sql", "note"]


def test_collect_sql_evidence_captures_counts():
    evidence = SecretManagementCheck().collect(_ctx())
    sql_ev = evidence[0]
    assert sql_ev.rows == [
        {"secret_ref_stmts": 12, "possible_hardcoded": 3, "total_stmts": 500}
    ]


def test_collect_note_evidence_flags_observability_gap():
    evidence = SecretManagementCheck().collect(_ctx())
    note_ev = evidence[1]
    assert note_ev.kind == "note"
    assert "Manual confirmation" in note_ev.summary
    assert note_ev.rows == []


def test_collect_empty_sql_still_returns_sql_and_note():
    evidence = SecretManagementCheck().collect(_ctx(sql_rows=[]))
    assert len(evidence) == 2
    sql_ev, note_ev = evidence
    assert sql_ev.kind == "sql"
    assert sql_ev.rows == []
    assert note_ev.kind == "note"


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = '{"verdict":"partial","confidence":"high","score":null,"rationale":"refs found"}'
    f = SecretManagementCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even when the model claims high.
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_no_llm_degrades_to_unassessed():
    f = SecretManagementCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
