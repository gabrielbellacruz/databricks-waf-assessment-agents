"""Tests for OrchestratedLineageCheck (ORC-DG-02)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.dg_lineage import OrchestratedLineageCheck

_Q = Question(
    id="ORC-DG-02",
    pillar_id="data-ai-governance",
    title="Track end-to-end lineage across orchestrated steps",
    principle="Lineage must be captured for every step in an orchestrated pipeline",
)

_LINEAGE_ROWS = [{"governed_tables": 80, "tables_with_lineage": 60}]
_JOBS_ROWS = [{"total_jobs": 20}]


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="test-orc-dg-02",
        layer="orchestration",
        sql=FakeSqlClient(
            {
                # Matches _SQL_LINEAGE (contains "table_lineage")
                "table_lineage": _LINEAGE_ROWS,
                # Matches _SQL_JOBS (contains "total_jobs")
                "total_jobs": _JOBS_ROWS,
            }
        ),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_two_evidences():
    ev = OrchestratedLineageCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_lineage_evidence_is_sql():
    ev = OrchestratedLineageCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"


def test_collect_lineage_summary_reflects_counts():
    ev = OrchestratedLineageCheck().collect(_ctx())
    assert "60" in ev[0].summary
    assert "80" in ev[0].summary


def test_collect_jobs_summary_reflects_count():
    ev = OrchestratedLineageCheck().collect(_ctx())
    assert "20" in ev[1].summary


def test_collect_evidence_rows_carry_data():
    ev = OrchestratedLineageCheck().collect(_ctx())
    assert ev[0].rows[0]["governed_tables"] == 80
    assert ev[0].rows[0]["tables_with_lineage"] == 60
    assert ev[1].rows[0]["total_jobs"] == 20


def test_judge_maps_llm_verdict_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some tables have lineage but not all steps covered"}'
    )
    f = OrchestratedLineageCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence capped at medium even when model claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "No lineage events recorded"}'
    )
    f = OrchestratedLineageCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Most tables have lineage captured"}'
    )
    f = OrchestratedLineageCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.auto_assessable is True


def test_no_llm_degrades_to_unassessed():
    f = OrchestratedLineageCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
