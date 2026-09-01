from __future__ import annotations

import json

from waf_agents.core.models import Confidence, Finding, Verdict
from waf_agents.core.store import DbConfig, ResultsStore

_CFG = DbConfig(
    host="db.example.com",
    port=5432,
    database="waf",
    user="sp-client-id",
    schema="waf",
    endpoint_name="projects/p/branches/b/endpoints/e",
)


class _RecordingStore(ResultsStore):
    """ResultsStore that captures executed SQL instead of touching Postgres."""

    def __init__(self, cfg: DbConfig) -> None:
        super().__init__(cfg, run_id="run-1", assessment_id="assessment-1", layer="ingestion")
        self.executed: list[tuple[str, tuple]] = []

    def _execute(self, sql: str, params: tuple) -> None:  # no DB in tests
        self.executed.append((sql, params))


def test_available_reflects_coordinates():
    assert _CFG.available is True
    assert DbConfig().available is False
    assert DbConfig(host="h", database="waf", user="u").available is False  # no endpoint


def test_mark_running_sets_total():
    s = _RecordingStore(_CFG)
    s.mark_running(7)
    sql, params = s.executed[0]
    assert "UPDATE agent_runs" in sql and "n_total" in sql
    assert params == (7, "run-1")


def test_progress_promotes_queued_and_sets_done():
    s = _RecordingStore(_CFG)
    s.update_progress(3)
    sql, params = s.executed[0]
    assert "n_done = %s" in sql and "queued" in sql
    assert params == (3, "run-1")


def test_write_done_inserts_findings_then_marks_done():
    s = _RecordingStore(_CFG)
    finding = Finding(
        question_id="ING-IU-03",
        pillar_id="interoperability",
        verdict=Verdict.MET,
        confidence=Confidence.HIGH,
        rationale="90% open formats",
        score=0.9,
    )
    s.write_done([finding])

    insert_sql, insert_params = s.executed[0]
    assert "INSERT INTO agent_findings" in insert_sql
    assert "ON CONFLICT (run_id, question_id) DO NOTHING" in insert_sql
    # (id, run_id, assessment_id, category_id, pillar_id, question_id, verdict,
    #  score, confidence, rationale, sources, auto_assessable)
    assert insert_params[1:9] == (
        "run-1",
        "assessment-1",
        "ingestion",  # category_id is the layer
        "interoperability",
        "ING-IU-03",
        "met",
        0.9,
        "high",
    )
    # sources is JSON-encoded text cast to jsonb in the SQL.
    assert json.loads(insert_params[10]) == []

    done_sql, done_params = s.executed[1]
    assert "status = 'done'" in done_sql and "finished_at = now()" in done_sql
    assert done_params == (1, "run-1")


def test_mark_failed_truncates_error():
    s = _RecordingStore(_CFG)
    s.mark_failed("boom")
    sql, params = s.executed[0]
    assert "status = 'failed'" in sql
    assert params == ("boom", "run-1")
