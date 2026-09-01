from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Question, Verdict
from waf_agents.processing.checks.scp_compute_isolation import ComputeIsolationCheck

_Q = Question(
    id="PRO-SCP-02",
    pillar_id="security-compliance-privacy",
    title="Use compute that supports user isolation",
    principle="Enforce per-user isolation on transformation compute",
)

_ISOLATED_ROWS = [
    {"data_security_mode": "SINGLE_USER", "cluster_count": 8},
    {"data_security_mode": "USER_ISOLATION", "cluster_count": 2},
]
_MIXED_ROWS = [
    {"data_security_mode": "SINGLE_USER", "cluster_count": 3},
    {"data_security_mode": "LEGACY", "cluster_count": 7},
]
_LEGACY_ROWS = [
    {"data_security_mode": "LEGACY", "cluster_count": 10},
]


def _ctx(rows: list[dict], llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient({"data_security_mode": rows}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_counts_isolated_clusters():
    ev = ComputeIsolationCheck().collect(_ctx(_ISOLATED_ROWS))
    assert ev[0].kind == "sql"
    assert "10 of 10" in ev[0].summary  # all 10 are SINGLE_USER or USER_ISOLATION


def test_collect_mixed_cluster_modes():
    ev = ComputeIsolationCheck().collect(_ctx(_MIXED_ROWS))
    assert "3 of 10" in ev[0].summary


def test_collect_no_clusters_handled():
    ev = ComputeIsolationCheck().collect(_ctx([]))
    assert "No active clusters" in ev[0].summary


def test_collect_returns_note_evidence():
    ev = ComputeIsolationCheck().collect(_ctx(_ISOLATED_ROWS))
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "SINGLE_USER" in ev[1].summary


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "All clusters use SINGLE_USER or USER_ISOLATION"}'
    )
    f = ComputeIsolationCheck().run(_Q, _ctx(_ISOLATED_ROWS, llm_response=resp))
    assert f.verdict is Verdict.MET


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "Most clusters are LEGACY with no user isolation"}'
    )
    f = ComputeIsolationCheck().run(_Q, _ctx(_LEGACY_ROWS, llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = ComputeIsolationCheck().run(_Q, _ctx(_MIXED_ROWS, llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
