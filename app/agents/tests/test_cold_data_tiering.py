from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.cold_data_tiering import ColdDataTieringCheck

_Q = Question(
    id="STO-CO-03",
    pillar_id="cost-optimization",
    title="Tier cold data to cheaper storage",
    principle="Move infrequently accessed data to cheaper storage tiers",
)

# Needles are distinct, non-overlapping substrings:
#   "total_tables"        -> _SQL_TOTAL  (AS total_tables)
#   "recently_read_tables" -> _SQL_RECENTLY_READ  (AS recently_read_tables)
_FAKE_RESPONSES = {
    "total_tables": [{"total_tables": 100}],
    "recently_read_tables": [{"recently_read_tables": 30}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_reports_cold_table_count():
    ev = ColdDataTieringCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    # 100 total - 30 recently read = 70 cold
    assert "70 of 100" in ev[0].summary


def test_collect_shows_cold_percentage():
    ev = ColdDataTieringCheck().collect(_ctx())
    # 70 / 100 = 70.0%
    assert "70.0%" in ev[0].summary


def test_collect_shows_recently_read_count():
    ev = ColdDataTieringCheck().collect(_ctx())
    assert "30 table(s)" in ev[0].summary


def test_collect_note_mentions_tiering_limitation():
    ev = ColdDataTieringCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "storage-class tiering" in ev[1].summary


def test_collect_evidence_has_rows():
    ev = ColdDataTieringCheck().collect(_ctx())
    row = ev[0].rows[0]
    assert row["total_tables"] == 100
    assert row["recently_read_tables"] == 30
    assert row["cold_tables"] == 70


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "not_met", "confidence": "high",'
        ' "score": null, "rationale": "70% of tables are cold with no tiering evidence"}'
    )
    f = ColdDataTieringCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_unknown_verdict():
    resp = (
        '{"verdict": "unknown", "confidence": "low",'
        ' "score": null, "rationale": "Cannot confirm tiering without manual verification"}'
    )
    f = ColdDataTieringCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_no_llm_degrades_to_unassessed():
    f = ColdDataTieringCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
