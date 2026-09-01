from __future__ import annotations

from waf_agents.ai.checks.co_model_choice import ModelChoiceCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-CO-01",
    pillar_id="cost-optimization",
    title="Match model choice to cost/quality needs",
    principle="Choose optimal resources",
)

# Distinct SQL needles:
#   "endpoint_usage"  -> _ENDPOINT_SQL (FROM system.serving.endpoint_usage)
#   "sku_name ILIKE"  -> _SKU_SQL      (AND sku_name ILIKE '%SERVING%')
_ENDPOINT_ROWS = [
    {"endpoint_name": "gpt4-premium", "request_count": 5000},
    {"endpoint_name": "llama-small", "request_count": 200},
]
_SKU_ROWS = [
    {"sku_name": "GPU_SERVING_PRO", "dbu": 1200.0},
    {"sku_name": "CPU_SERVING_STD", "dbu": 100.0},
]


def _ctx(
    *,
    endpoint_rows: list[dict] | None = None,
    sku_rows: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    responses: dict[str, list[dict]] = {}
    if endpoint_rows is not None:
        responses["endpoint_usage"] = endpoint_rows
    if sku_rows is not None:
        responses["sku_name ILIKE"] = sku_rows
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(responses),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidence_items():
    ev = ModelChoiceCheck().collect(_ctx(endpoint_rows=_ENDPOINT_ROWS, sku_rows=_SKU_ROWS))
    assert len(ev) == 3
    kinds = [e.kind for e in ev]
    assert kinds.count("sql") == 2
    assert kinds.count("note") == 1


def test_collect_endpoint_summary_includes_names():
    ev = ModelChoiceCheck().collect(_ctx(endpoint_rows=_ENDPOINT_ROWS, sku_rows=[]))
    assert "gpt4-premium" in ev[0].summary
    assert "5000" in ev[0].summary


def test_collect_sku_summary_includes_sku_names():
    ev = ModelChoiceCheck().collect(_ctx(endpoint_rows=[], sku_rows=_SKU_ROWS))
    assert "GPU_SERVING_PRO" in ev[1].summary


def test_collect_empty_endpoints_summary():
    ev = ModelChoiceCheck().collect(_ctx(endpoint_rows=[], sku_rows=[]))
    assert "No serving endpoint usage" in ev[0].summary


def test_collect_note_mentions_limitation():
    ev = ModelChoiceCheck().collect(_ctx(endpoint_rows=[], sku_rows=[]))
    note = next(e for e in ev if e.kind == "note")
    assert "system tables" in note.summary


def test_judge_maps_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Premium model dominates cheap requests"}'
    )
    ctx = _ctx(endpoint_rows=_ENDPOINT_ROWS, sku_rows=_SKU_ROWS, llm_response=resp)
    f = ModelChoiceCheck().run(_Q, ctx)
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_caps_high_confidence_to_medium():
    resp = (
        '{"verdict": "not_met", "confidence": "high",'
        ' "score": null, "rationale": "All requests go to premium model"}'
    )
    ctx = _ctx(endpoint_rows=_ENDPOINT_ROWS, sku_rows=_SKU_ROWS, llm_response=resp)
    f = ModelChoiceCheck().run(_Q, ctx)
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_returns_unassessed_with_sources():
    ctx = _ctx(endpoint_rows=_ENDPOINT_ROWS, sku_rows=_SKU_ROWS, llm_response=None)
    f = ModelChoiceCheck().run(_Q, ctx)
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
