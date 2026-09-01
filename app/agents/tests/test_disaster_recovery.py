from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.disaster_recovery import DisasterRecoveryCheck

_Q = Question(
    id="STO-R-03",
    pillar_id="reliability",
    title="Configure a disaster-recovery pattern for storage",
    principle="Design for recoverability",
)

# Needles are distinct, non-overlapping substrings of the two SQL queries:
#   "clone_stmts"    -> _CLONE_SQL    (column alias unique to that query)
#   "catalog_count"  -> _CATALOGS_SQL (column alias unique to that query)
_FAKE_RESPONSES = {
    "clone_stmts": [{"deep_clone_stmts": 8, "clone_stmts": 11}],
    "catalog_count": [{"catalog_count": 3}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_clone_evidence():
    ev = DisasterRecoveryCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "DEEP CLONE=8" in ev[0].summary
    assert "total CLONE=11" in ev[0].summary


def test_collect_catalog_evidence():
    ev = DisasterRecoveryCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "3 distinct UC catalogs" in ev[1].summary


def test_collect_observability_note():
    ev = DisasterRecoveryCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[2].kind == "note"
    assert "Cross-region" in ev[2].summary


def test_collect_evidence_rows():
    ev = DisasterRecoveryCheck().collect(_ctx())
    assert ev[0].rows[0]["deep_clone_stmts"] == 8
    assert ev[0].rows[0]["clone_stmts"] == 11
    assert ev[1].rows[0]["catalog_count"] == 3


def test_collect_shallow_clone_derived():
    ev = DisasterRecoveryCheck().collect(_ctx())
    # shallow = total - deep = 11 - 8 = 3
    assert "SHALLOW CLONE=3" in ev[0].summary


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "DEEP CLONE usage seen but cross-region unknown"}'
    )
    f = DisasterRecoveryCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_unknown_verdict():
    resp = (
        '{"verdict": "unknown", "confidence": "low",'
        ' "score": null, "rationale": "Cannot determine DR posture from available proxies"}'
    )
    f = DisasterRecoveryCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_no_llm_degrades_to_unassessed():
    f = DisasterRecoveryCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
