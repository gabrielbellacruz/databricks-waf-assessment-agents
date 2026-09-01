from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.time_travel import TimeTravelCheck

_Q = Question(
    id="STO-R-02",
    pillar_id="reliability",
    title="Recover stored data using time travel",
    principle="Design for recoverability",
)

# Needles are distinct, non-overlapping substrings of the two SQL queries:
#   "data_source_format"  -> _DELTA_TABLES_SQL
#   "VERSION AS OF"       -> _TIME_TRAVEL_SQL (substring of '%VERSION AS OF%')
_FAKE_RESPONSES = {
    "data_source_format": [{"total_tables": 80, "delta_tables": 64}],
    "VERSION AS OF": [
        {
            "restore_stmts": 5,
            "version_as_of_stmts": 12,
            "timestamp_as_of_stmts": 3,
        }
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


def test_collect_delta_adoption():
    ev = TimeTravelCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "64 of 80" in ev[0].summary
    assert "80.0%" in ev[0].summary


def test_collect_time_travel_usage():
    ev = TimeTravelCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "RESTORE=5" in ev[1].summary
    assert "VERSION AS OF=12" in ev[1].summary
    assert "TIMESTAMP AS OF=3" in ev[1].summary
    assert "total=20" in ev[1].summary


def test_collect_retention_note():
    ev = TimeTravelCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[2].kind == "note"
    assert "delta.logRetentionDuration" in ev[2].summary


def test_collect_evidence_rows():
    ev = TimeTravelCheck().collect(_ctx())
    assert ev[0].rows[0]["delta_tables"] == 64
    assert ev[1].rows[0]["version_as_of_stmts"] == 12


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Delta adoption is high but retention window unknown"}'
    )
    f = TimeTravelCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "High Delta adoption and frequent time-travel usage"}'
    )
    f = TimeTravelCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = TimeTravelCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
