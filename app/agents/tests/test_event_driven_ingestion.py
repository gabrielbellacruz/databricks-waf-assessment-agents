"""Tests for EventDrivenIngestionCheck (ING-OE-01)."""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.event_driven_ingestion import EventDrivenIngestionCheck

_Q = Question(
    id="ING-OE-01",
    pillar_id="operational-excellence",
    title="Use automated, event-driven file ingestion",
    principle="Automate ingestion workflows to reduce manual toil",
)

# Fake SQL rows — keyed on distinct substrings of the two SQL strings the check runs.
_JOBS_ROWS = [{"total_jobs": 10, "file_arrival_jobs": 4}]
_AUTOLOADER_ROWS = [{"autoloader_statements": 25}]


def _sql_client() -> FakeSqlClient:
    return FakeSqlClient(
        {
            # Matches _SQL_FILE_ARRIVAL (contains "system.lakeflow.jobs")
            "system.lakeflow.jobs": _JOBS_ROWS,
            # Matches _SQL_AUTOLOADER (contains "cloud_files")
            "cloud_files": _AUTOLOADER_ROWS,
        }
    )


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="test-edi-01",
        layer="ingestion",
        sql=_sql_client(),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect()
# ---------------------------------------------------------------------------


def test_collect_returns_two_evidences():
    ev = EventDrivenIngestionCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_evidences_are_sql_kind():
    ev = EventDrivenIngestionCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"


def test_collect_file_arrival_summary_reflects_counts():
    ev = EventDrivenIngestionCheck().collect(_ctx())
    assert "4 of 10 jobs" in ev[0].summary
    assert "file-arrival trigger" in ev[0].summary


def test_collect_autoloader_summary_reflects_count():
    ev = EventDrivenIngestionCheck().collect(_ctx())
    assert "25" in ev[1].summary
    # summary must name either the format or the feature
    assert "cloud_files" in ev[1].summary or "Auto Loader" in ev[1].summary


def test_collect_evidence_rows_carry_counts():
    ev = EventDrivenIngestionCheck().collect(_ctx())
    assert ev[0].rows == [{"total_jobs": 10, "file_arrival_jobs": 4}]
    assert ev[1].rows == [{"autoloader_statements": 25}]


def test_collect_evidence_has_autoloader_ref():
    ev = EventDrivenIngestionCheck().collect(_ctx())
    for e in ev:
        assert e.ref is not None
        assert "auto-loader" in e.ref


def test_collect_with_zero_counts():
    sql = FakeSqlClient(
        {
            "system.lakeflow.jobs": [{"total_jobs": 0, "file_arrival_jobs": 0}],
            "cloud_files": [{"autoloader_statements": 0}],
        }
    )
    ctx = AgentContext(assessment_id="test-edi-zeros", layer="ingestion", sql=sql)
    ev = EventDrivenIngestionCheck().collect(ctx)
    assert "0 of 0 jobs" in ev[0].summary
    assert "0 Auto Loader" in ev[1].summary


def test_collect_with_empty_sql_result():
    """Empty rows from SQL (permission denied / table absent) -> zero counts, no crash."""
    ctx = AgentContext(
        assessment_id="test-edi-empty",
        layer="ingestion",
        sql=FakeSqlClient(),  # no responses -> always returns []
    )
    ev = EventDrivenIngestionCheck().collect(ctx)
    assert len(ev) == 2
    assert "0 of 0 jobs" in ev[0].summary
    assert "0 Auto Loader" in ev[1].summary


# ---------------------------------------------------------------------------
# judge() via run()
# ---------------------------------------------------------------------------


def test_judge_maps_partial_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "some jobs use file-arrival"}'
    )
    f = EventDrivenIngestionCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even when the model claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources  # evidence attached for explainability


def test_judge_met_verdict_low_confidence():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "all signals indicate broad adoption"}'
    )
    f = EventDrivenIngestionCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.auto_assessable is True


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "low",'
        ' "score": null, "rationale": "no file-arrival triggers found"}'
    )
    f = EventDrivenIngestionCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_degrades_to_unassessed():
    f = EventDrivenIngestionCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached even without an LLM
