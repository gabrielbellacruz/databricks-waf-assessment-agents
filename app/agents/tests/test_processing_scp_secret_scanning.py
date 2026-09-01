from __future__ import annotations

from waf_agents.core.clients import (
    AgentContext,
    FakeArtifactClient,
    FakeLlmClient,
    FakeSqlClient,
)
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.scp_secret_scanning import SecretScanningCheck

_Q = Question(
    id="PRO-SCP-05",
    pillar_id="security-compliance-privacy",
    title="Scan pipeline code for hard-coded secrets in CI",
    principle="Integrate secret scanning into the CI pipeline for transformation code",
)

_CLEAN_QH = [{"possible_hardcoded": 0, "total_stmts": 500}]
_RISK_QH = [{"possible_hardcoded": 3, "total_stmts": 500}]


def _ctx(
    jobs: list[dict] | None = None,
    pipelines: list[dict] | None = None,
    qh_rows: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient({"possible_hardcoded": qh_rows if qh_rows is not None else _CLEAN_QH}),
        catalogs=["main"],
        artifacts=FakeArtifactClient(jobs=jobs or [], pipelines=pipelines or []),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_git_coverage_evidence():
    jobs = [{"settings": {"git_source": {"url": "https://github.com/x"}}}]
    ev = SecretScanningCheck().collect(_ctx(jobs=jobs))
    git_ev = next(e for e in ev if e.kind == "job_config")
    assert "1 of 1" in git_ev.summary
    assert "Git-backed" in git_ev.summary


def test_collect_clean_query_history():
    ev = SecretScanningCheck().collect(_ctx())
    qh_ev = next(e for e in ev if e.kind == "sql")
    assert "0 of 500" in qh_ev.summary


def test_collect_risk_query_history():
    ev = SecretScanningCheck().collect(_ctx(qh_rows=_RISK_QH))
    qh_ev = next(e for e in ev if e.kind == "sql")
    assert "3 of 500" in qh_ev.summary


def test_collect_returns_note_evidence():
    ev = SecretScanningCheck().collect(_ctx())
    note = next((e for e in ev if e.kind == "note"), None)
    assert note is not None
    assert "CI" in note.summary


def test_collect_no_artifacts_still_has_sql_and_note():
    ctx = AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient({"possible_hardcoded": _CLEAN_QH}),
        catalogs=["main"],
        artifacts=None,
        llm=FakeLlmClient(""),
    )
    ev = SecretScanningCheck().collect(ctx)
    # No job_config evidence without artifacts
    kinds = [e.kind for e in ev]
    assert "job_config" not in kinds
    assert "sql" in kinds
    assert "note" in kinds


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "All code is git-backed and no hard-coded patterns"}'
    )
    jobs = [{"settings": {"git_source": {"url": "https://github.com/x"}}}]
    f = SecretScanningCheck().run(_Q, _ctx(jobs=jobs, llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "No git-backed code and hard-coded patterns found"}'
    )
    f = SecretScanningCheck().run(_Q, _ctx(qh_rows=_RISK_QH, llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = SecretScanningCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
