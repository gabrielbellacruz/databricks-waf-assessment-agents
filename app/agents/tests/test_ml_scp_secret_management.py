from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.scp_secret_management import MlSecretManagementCheck

_Q = Question(
    id="ML-SCP-03",
    pillar_id="security-compliance-privacy",
    title="Keep secrets out of training/serving code",
    principle="Manage credentials securely in ML pipelines",
)

_LLM_MET = (
    '{"verdict": "met", "confidence": "medium", "score": null,'
    ' "rationale": "High secret() usage with no hard-coded patterns."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "medium", "score": null,'
    ' "rationale": "Hard-coded credential patterns found in query history."}'
)


def _ctx(
    *,
    llm_response: str | None = _LLM_MET,
    sql_rows: list[dict] | None = None,
) -> AgentContext:
    # Needle for the query.history SQL — "secret_ref_stmts" column
    responses = {
        "secret_ref_stmts": sql_rows if sql_rows is not None else [
            {
                "secret_ref_stmts": 45,
                "possible_hardcoded": 2,
                "total_stmts": 1000,
            }
        ]
    }
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(responses),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_two_entries():
    ev = MlSecretManagementCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_shows_counts():
    ev = MlSecretManagementCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "45" in ev[0].summary  # secret_ref_stmts
    assert "2" in ev[0].summary   # possible_hardcoded
    assert ev[0].rows[0]["secret_ref_stmts"] == 45
    assert ev[0].rows[0]["possible_hardcoded"] == 2
    assert ev[0].rows[0]["total_stmts"] == 1000


def test_collect_note_evidence_present():
    ev = MlSecretManagementCheck().collect(_ctx())
    note = ev[1]
    assert note.kind == "note"
    assert note.rows == []


def test_collect_empty_sql_produces_safe_summary():
    ctx = AgentContext(
        assessment_id="t2",
        layer="ml",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = MlSecretManagementCheck().collect(ctx)
    assert "No query-history rows" in ev[0].summary
    assert ev[0].rows == []


def test_collect_note_mentions_serving():
    ev = MlSecretManagementCheck().collect(_ctx())
    note_text = ev[1].summary.lower()
    assert "serving" in note_text or "notebook" in note_text


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_met_verdict():
    f = MlSecretManagementCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    f = MlSecretManagementCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET


def test_judge_confidence_capped_at_medium():
    resp = (
        '{"verdict": "partial", "confidence": "high", "score": null,'
        ' "rationale": "Mostly using secrets."}'
    )
    f = MlSecretManagementCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_sql_and_note():
    f = MlSecretManagementCheck().run(_Q, _ctx(llm_response=_LLM_MET))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = MlSecretManagementCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
