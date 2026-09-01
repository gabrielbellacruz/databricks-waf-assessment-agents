from __future__ import annotations

from waf_agents.ai.checks.co_cost_attribution import CostAttributionCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-CO-04",
    pillar_id="cost-optimization",
    title="Track and attribute token/endpoint cost",
    principle="Monitor and control cost",
)

# Distinct SQL needles:
#   "custom_tags"   -> _TAG_SQL     (CASE WHEN custom_tags IS NOT NULL)
#   "ai_gateway.usage" -> _GATEWAY_SQL  (FROM system.ai_gateway.usage)
_TAG_ROWS_TAGGED = [{"total": 100, "tagged": 80}]
_TAG_ROWS_UNTAGGED = [{"total": 100, "tagged": 5}]
_GATEWAY_ROWS_PRESENT = [{"request_count": 500, "input_tokens": 200000, "output_tokens": 150000}]
_GATEWAY_ROWS_EMPTY = [{"request_count": 0, "input_tokens": 0, "output_tokens": 0}]


def _ctx(
    *,
    tag_rows: list[dict] | None = None,
    gw_rows: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    responses: dict[str, list[dict]] = {}
    if tag_rows is not None:
        responses["custom_tags"] = tag_rows
    if gw_rows is not None:
        responses["ai_gateway.usage"] = gw_rows
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(responses),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidence_items():
    ctx = _ctx(tag_rows=_TAG_ROWS_TAGGED, gw_rows=_GATEWAY_ROWS_PRESENT)
    ev = CostAttributionCheck().collect(ctx)
    assert len(ev) == 3
    kinds = [e.kind for e in ev]
    assert kinds.count("sql") == 2
    assert kinds.count("note") == 1


def test_collect_tag_summary_shows_coverage():
    ev = CostAttributionCheck().collect(_ctx(tag_rows=_TAG_ROWS_TAGGED, gw_rows=[]))
    # 80/100 = 80%
    assert "80" in ev[0].summary
    assert "100" in ev[0].summary
    assert "80.0%" in ev[0].summary


def test_collect_tag_rows_include_tagged_pct():
    ev = CostAttributionCheck().collect(_ctx(tag_rows=_TAG_ROWS_TAGGED, gw_rows=[]))
    assert ev[0].rows[0]["tagged_pct"] == 80.0


def test_collect_gateway_summary_shows_request_count():
    ev = CostAttributionCheck().collect(_ctx(tag_rows=[], gw_rows=_GATEWAY_ROWS_PRESENT))
    assert "500" in ev[1].summary


def test_collect_gateway_summary_no_data():
    ev = CostAttributionCheck().collect(_ctx(tag_rows=[], gw_rows=_GATEWAY_ROWS_EMPTY))
    assert "No AI Gateway usage" in ev[1].summary


def test_collect_no_billing_data():
    ev = CostAttributionCheck().collect(_ctx(tag_rows=[], gw_rows=[]))
    assert "No serving billing usage" in ev[0].summary


def test_collect_note_mentions_rate_limits():
    ev = CostAttributionCheck().collect(_ctx(tag_rows=[], gw_rows=[]))
    note = next(e for e in ev if e.kind == "note")
    assert "rate-limit" in note.summary or "Rate-limit" in note.summary


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "High tag coverage and AI Gateway active"}'
    )
    f = CostAttributionCheck().run(
        _Q, _ctx(tag_rows=_TAG_ROWS_TAGGED, gw_rows=_GATEWAY_ROWS_PRESENT, llm_response=resp)
    )
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_low_tags_no_gateway():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "Only 5% of records tagged; no AI Gateway"}'
    )
    f = CostAttributionCheck().run(
        _Q, _ctx(tag_rows=_TAG_ROWS_UNTAGGED, gw_rows=_GATEWAY_ROWS_EMPTY, llm_response=resp)
    )
    assert f.verdict is Verdict.NOT_MET


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Gateway present but low tag coverage"}'
    )
    f = CostAttributionCheck().run(
        _Q, _ctx(tag_rows=_TAG_ROWS_TAGGED, gw_rows=_GATEWAY_ROWS_PRESENT, llm_response=resp)
    )
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_returns_unassessed_with_sources():
    f = CostAttributionCheck().run(
        _Q, _ctx(tag_rows=_TAG_ROWS_TAGGED, gw_rows=_GATEWAY_ROWS_PRESENT, llm_response=None)
    )
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
