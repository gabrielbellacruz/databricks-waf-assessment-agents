from __future__ import annotations

from waf_agents.ai.checks.co_token_caching import TokenCachingCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-CO-02",
    pillar_id="cost-optimization",
    title="Cache to reduce token consumption",
    principle="Design cost-effective workloads",
)

# Distinct SQL needle: "cache_read_input_tokens" appears in _CACHE_SQL column expression.
_CACHE_ROWS_WITH_CACHING = [
    {
        "request_count": 1000,
        "total_input_tokens": 500000,
        "cache_read_tokens": 200000,
        "cache_creation_tokens": 50000,
        "total_output_tokens": 300000,
    }
]
_CACHE_ROWS_NO_CACHING = [
    {
        "request_count": 1000,
        "total_input_tokens": 500000,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "total_output_tokens": 300000,
    }
]


def _ctx(*, cache_rows: list[dict] | None = None, llm_response: str | None = "") -> AgentContext:
    responses: dict[str, list[dict]] = {}
    if cache_rows is not None:
        responses["cache_read_input_tokens"] = cache_rows
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(responses),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_two_evidence_items():
    ev = TokenCachingCheck().collect(_ctx(cache_rows=_CACHE_ROWS_WITH_CACHING))
    assert len(ev) == 2
    assert ev[0].kind == "sql"
    assert ev[1].kind == "note"


def test_collect_summary_shows_cache_read_percentage():
    ev = TokenCachingCheck().collect(_ctx(cache_rows=_CACHE_ROWS_WITH_CACHING))
    # 200000 / 500000 = 40.0%
    assert "40.0%" in ev[0].summary


def test_collect_summary_shows_request_count():
    ev = TokenCachingCheck().collect(_ctx(cache_rows=_CACHE_ROWS_WITH_CACHING))
    assert "1000" in ev[0].summary


def test_collect_rows_include_cache_read_pct():
    ev = TokenCachingCheck().collect(_ctx(cache_rows=_CACHE_ROWS_WITH_CACHING))
    assert ev[0].rows[0]["cache_read_pct"] == 40.0


def test_collect_no_gateway_usage_summary():
    ev = TokenCachingCheck().collect(_ctx(cache_rows=[]))
    assert "No AI Gateway usage" in ev[0].summary


def test_collect_note_mentions_limitation():
    ev = TokenCachingCheck().collect(_ctx(cache_rows=[]))
    assert "AI Gateway" in ev[1].summary


def test_judge_met_when_caching_active():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "40% cache hit rate shows caching is active"}'
    )
    f = TokenCachingCheck().run(_Q, _ctx(cache_rows=_CACHE_ROWS_WITH_CACHING, llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_when_no_caching():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "Zero cache_read tokens — caching not in use"}'
    )
    f = TokenCachingCheck().run(_Q, _ctx(cache_rows=_CACHE_ROWS_NO_CACHING, llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some caching but incomplete"}'
    )
    f = TokenCachingCheck().run(_Q, _ctx(cache_rows=_CACHE_ROWS_WITH_CACHING, llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_returns_unassessed_with_sources():
    f = TokenCachingCheck().run(_Q, _ctx(cache_rows=_CACHE_ROWS_WITH_CACHING, llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
