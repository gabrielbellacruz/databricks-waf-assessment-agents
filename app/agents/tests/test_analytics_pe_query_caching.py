from __future__ import annotations

from waf_agents.analytics.checks.pe_query_caching import QueryCachingCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-PE-03",
    pillar_id="performance-efficiency",
    title="Leverage caching for repeated queries",
    principle="Serve repeated analytics queries from cache to reduce latency",
)

# Needle: "from_result_cache" is a unique column reference in _CACHE_SQL.
# from_result_cache is a BOOLEAN flag (cache hit), not a byte count, so the
# check reports a hit rate only — there is no total_cache_bytes metric.
_FAKE_RESPONSES = {
    "from_result_cache": [
        {"total_queries": 200, "cache_hit_queries": 40}
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_two_evidences():
    ev = QueryCachingCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    assert ev[1].kind == "note"


def test_collect_summary_contains_hit_rate():
    ev = QueryCachingCheck().collect(_ctx())
    # 40/200 = 20.0%
    assert "40 of 200" in ev[0].summary
    assert "20.0%" in ev[0].summary


def test_collect_summary_reports_hit_rate_not_bytes():
    # from_result_cache is boolean, so the summary is a hit-rate only — there
    # is no byte/GB volume metric to report.
    ev = QueryCachingCheck().collect(_ctx())
    assert "served from cache" in ev[0].summary
    assert "GB" not in ev[0].summary
    assert "bytes" not in ev[0].summary.lower()


def test_collect_evidence_rows():
    ev = QueryCachingCheck().collect(_ctx())
    row = ev[0].rows[0]
    assert row["total_queries"] == 200
    assert row["cache_hit_queries"] == 40
    assert "total_cache_bytes" not in row


def test_judge_maps_llm_verdict_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "20% cache hit rate, improvement possible"}'
    )
    f = QueryCachingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "High cache utilization across warehouse queries"}'
    )
    f = QueryCachingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET


def test_no_llm_degrades_to_unassessed():
    f = QueryCachingCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
