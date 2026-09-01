from __future__ import annotations

from waf_agents.ai.checks.co_scale_to_zero import ScaleToZeroCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-CO-05",
    pillar_id="cost-optimization",
    title="Scale endpoints to zero when idle",
    principle="Dynamically allocate resources",
)

# Distinct SQL needles:
#   "idle_days"   -> _IDLE_SQL    (AS idle_days)
#   "serving_dbu" -> _BILLING_SQL (AS serving_dbu)
_IDLE_ROWS_WITH_IDLE = [
    {"endpoint_name": "llm-infer", "days_active": 30, "idle_days": 20, "total_requests": 500},
    {"endpoint_name": "embed-model", "days_active": 30, "idle_days": 25, "total_requests": 100},
]
_IDLE_ROWS_ALL_ACTIVE = [
    {"endpoint_name": "chat-prod", "days_active": 30, "idle_days": 0, "total_requests": 50000},
]
_BILLING_ROWS = [{"serving_dbu": 1500.0}]


def _ctx(
    *,
    idle_rows: list[dict] | None = None,
    billing_rows: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    responses: dict[str, list[dict]] = {}
    if idle_rows is not None:
        responses["idle_days"] = idle_rows
    if billing_rows is not None:
        responses["serving_dbu"] = billing_rows
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(responses),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidence_items():
    ctx = _ctx(idle_rows=_IDLE_ROWS_WITH_IDLE, billing_rows=_BILLING_ROWS)
    ev = ScaleToZeroCheck().collect(ctx)
    assert len(ev) == 3
    kinds = [e.kind for e in ev]
    assert kinds.count("sql") == 2
    assert kinds.count("note") == 1


def test_collect_idle_summary_shows_endpoint_count():
    ctx = _ctx(idle_rows=_IDLE_ROWS_WITH_IDLE, billing_rows=_BILLING_ROWS)
    ev = ScaleToZeroCheck().collect(ctx)
    assert "2 endpoints" in ev[0].summary


def test_collect_idle_summary_shows_idle_endpoint_count():
    ctx = _ctx(idle_rows=_IDLE_ROWS_WITH_IDLE, billing_rows=_BILLING_ROWS)
    ev = ScaleToZeroCheck().collect(ctx)
    # Both endpoints have idle_days > 0
    assert "2 have at least one idle day" in ev[0].summary


def test_collect_idle_summary_total_idle_days():
    ctx = _ctx(idle_rows=_IDLE_ROWS_WITH_IDLE, billing_rows=_BILLING_ROWS)
    ev = ScaleToZeroCheck().collect(ctx)
    # 20 + 25 = 45
    assert "45" in ev[0].summary


def test_collect_billing_summary_shows_dbu():
    ev = ScaleToZeroCheck().collect(_ctx(idle_rows=[], billing_rows=_BILLING_ROWS))
    assert "1500.0" in ev[1].summary


def test_collect_no_endpoint_usage():
    ev = ScaleToZeroCheck().collect(_ctx(idle_rows=[], billing_rows=[]))
    assert "No serving endpoint usage" in ev[0].summary


def test_collect_note_mentions_scale_to_zero():
    ev = ScaleToZeroCheck().collect(_ctx(idle_rows=[], billing_rows=[]))
    note = next(e for e in ev if e.kind == "note")
    assert "scale-to-zero" in note.summary or "Scale-to-zero" in note.summary


def test_judge_not_met_with_idle_endpoints():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "Endpoints idle 20+ days with active billing"}'
    )
    f = ScaleToZeroCheck().run(
        _Q, _ctx(idle_rows=_IDLE_ROWS_WITH_IDLE, billing_rows=_BILLING_ROWS, llm_response=resp)
    )
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_met_no_idle_endpoints():
    resp = (
        '{"verdict": "met", "confidence": "low",'
        ' "score": null, "rationale": "No idle days detected on any endpoint"}'
    )
    f = ScaleToZeroCheck().run(
        _Q, _ctx(idle_rows=_IDLE_ROWS_ALL_ACTIVE, billing_rows=_BILLING_ROWS, llm_response=resp)
    )
    assert f.verdict is Verdict.MET


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some idle endpoints but billing is moderate"}'
    )
    f = ScaleToZeroCheck().run(
        _Q, _ctx(idle_rows=_IDLE_ROWS_WITH_IDLE, billing_rows=_BILLING_ROWS, llm_response=resp)
    )
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_returns_unassessed_with_sources():
    f = ScaleToZeroCheck().run(
        _Q, _ctx(idle_rows=_IDLE_ROWS_WITH_IDLE, billing_rows=_BILLING_ROWS, llm_response=None)
    )
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
