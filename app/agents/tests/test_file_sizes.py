from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.file_sizes import FileSizesCheck

_Q = Question(
    id="STO-PE-02",
    pillar_id="performance-efficiency",
    title="Maintain healthy file sizes in storage",
    principle="Ensure Delta tables use compacted, right-sized files",
)

# Needle: "vacuum_stmts" appears as a column alias in FileSizesCheck._SQL.
_FAKE_RESPONSES = {
    "vacuum_stmts": [
        {"optimize_stmts": 20, "vacuum_stmts": 8, "total_stmts": 900}
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


def test_collect_returns_two_evidences():
    ev = FileSizesCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    assert ev[1].kind == "note"


def test_collect_sql_summary_contains_optimize_count():
    ev = FileSizesCheck().collect(_ctx())
    assert "OPTIMIZE=20" in ev[0].summary


def test_collect_sql_summary_contains_vacuum_count():
    ev = FileSizesCheck().collect(_ctx())
    assert "VACUUM=8" in ev[0].summary


def test_collect_sql_evidence_has_rows():
    ev = FileSizesCheck().collect(_ctx())
    assert ev[0].rows[0]["optimize_stmts"] == 20
    assert ev[0].rows[0]["vacuum_stmts"] == 8
    assert ev[0].rows[0]["total_stmts"] == 900


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some OPTIMIZE runs observed but infrequent"}'
    )
    f = FileSizesCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "low",'
        ' "score": null, "rationale": "No OPTIMIZE commands found"}'
    )
    f = FileSizesCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.LOW


def test_no_llm_degrades_to_unassessed():
    f = FileSizesCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
