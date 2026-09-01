"""Tests for CheckpointRecoveryCheck (ING-R-03).

Covers:
  - collect() returns a sql evidence block and a note evidence block
  - sql evidence rows contain the expected count keys
  - judge() maps a canned LLM JSON response to the correct Finding fields
  - LLM confidence is capped at medium even when the model claims high
  - llm=None degrades gracefully to an unassessed finding (evidence still attached)
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.checkpoint_recovery import CheckpointRecoveryCheck

_Q = Question(
    id="ING-R-03",
    pillar_id="reliability",
    title="Recover streaming ingestion from checkpoint failures",
    principle="Design for reliability",
)

_HISTORY_ROWS = [
    {
        "checkpoint_stmts": "12",
        "streaming_stmts": "47",
        "total_stmts": "350",
    }
]


def _ctx(*, sql_rows: list[dict] | None = None, llm_response: str | None = "") -> AgentContext:
    responses: dict[str, list[dict]] = {}
    if sql_rows is not None:
        responses["system.query.history"] = sql_rows
    return AgentContext(
        assessment_id="test-a1",
        layer="ingestion",
        sql=FakeSqlClient(responses),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() behaviour
# ---------------------------------------------------------------------------


def test_collect_returns_sql_and_note_evidence():
    evidence = CheckpointRecoveryCheck().collect(_ctx(sql_rows=_HISTORY_ROWS))
    kinds = [e.kind for e in evidence]
    assert "sql" in kinds
    assert "note" in kinds


def test_collect_sql_evidence_contains_counts():
    evidence = CheckpointRecoveryCheck().collect(_ctx(sql_rows=_HISTORY_ROWS))
    sql_ev = next(e for e in evidence if e.kind == "sql")
    assert sql_ev.rows
    row = sql_ev.rows[0]
    assert row["checkpoint_stmts"] == 12
    assert row["streaming_stmts"] == 47
    assert row["total_stmts"] == 350


def test_collect_note_evidence_has_no_rows():
    evidence = CheckpointRecoveryCheck().collect(_ctx(sql_rows=_HISTORY_ROWS))
    note_ev = next(e for e in evidence if e.kind == "note")
    assert note_ev.rows == []
    assert "Manual confirmation" in note_ev.summary


def test_collect_sql_evidence_mentions_checkpoint_in_summary():
    evidence = CheckpointRecoveryCheck().collect(_ctx(sql_rows=_HISTORY_ROWS))
    sql_ev = next(e for e in evidence if e.kind == "sql")
    assert "checkpoint" in sql_ev.summary.lower()


def test_collect_no_rows_returns_two_evidence_items():
    """Empty query result still produces two evidence items (sql + note)."""
    evidence = CheckpointRecoveryCheck().collect(_ctx(sql_rows=[]))
    assert len(evidence) == 2
    kinds = {e.kind for e in evidence}
    assert kinds == {"sql", "note"}


# ---------------------------------------------------------------------------
# judge() / run() behaviour
# ---------------------------------------------------------------------------


def test_judge_maps_llm_verdict_partial():
    canned = (
        '{"verdict": "partial", "confidence": "medium", "score": null,'
        ' "rationale": "Checkpoint usage found but no evidence of recovery testing."}'
    )
    finding = CheckpointRecoveryCheck().run(_Q, _ctx(sql_rows=_HISTORY_ROWS, llm_response=canned))
    assert finding.verdict is Verdict.PARTIAL
    assert finding.confidence is Confidence.MEDIUM
    assert finding.sources


def test_judge_maps_llm_verdict_met():
    canned = (
        '{"verdict": "met", "confidence": "medium", "score": null,'
        ' "rationale": "High checkpoint usage signals restartable streams."}'
    )
    finding = CheckpointRecoveryCheck().run(_Q, _ctx(sql_rows=_HISTORY_ROWS, llm_response=canned))
    assert finding.verdict is Verdict.MET
    assert finding.confidence is Confidence.MEDIUM


def test_judge_caps_llm_confidence_at_medium():
    """LLM claims high confidence — must be capped at medium."""
    canned = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "Strong checkpoint evidence."}'
    )
    finding = CheckpointRecoveryCheck().run(_Q, _ctx(sql_rows=_HISTORY_ROWS, llm_response=canned))
    assert finding.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed_with_evidence():
    """When ctx.llm is None the finding is unassessed but evidence is still attached."""
    finding = CheckpointRecoveryCheck().run(_Q, _ctx(sql_rows=_HISTORY_ROWS, llm_response=None))
    assert finding.verdict is Verdict.UNKNOWN
    assert finding.auto_assessable is False
    assert finding.sources
