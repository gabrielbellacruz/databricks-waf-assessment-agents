from __future__ import annotations

from waf_agents.ai.checks.oe_eval_benchmarks import EvalBenchmarksCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-OE-01",
    pillar_id="oe",
    title="Compare LLM outputs on a fixed prompt set",
    principle="Establish a repeatable evaluation baseline",
)

# SQL needles — distinct substrings from the two query strings
_FAKE = {
    "endpoint_usage": [{"distinct_endpoints": 3, "total_requests": 1200}],
    "ai_gateway.usage": [{"gateway_endpoints": 2, "total_gateway_calls": 500}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_endpoint_evidence():
    ev = EvalBenchmarksCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "3 distinct" in ev[0].summary
    assert "1200" in ev[0].summary


def test_collect_gateway_evidence():
    ev = EvalBenchmarksCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "2" in ev[1].summary
    assert "500" in ev[1].summary


def test_collect_note_evidence():
    ev = EvalBenchmarksCheck().collect(_ctx())
    assert ev[2].kind == "note"
    assert "NOT observable" in ev[2].summary


def test_collect_empty_returns_no_data_summary():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        llm=FakeLlmClient(""),
    )
    ev = EvalBenchmarksCheck().collect(ctx)
    assert "No rows" in ev[0].summary or "No data" in ev[0].summary


def test_judge_maps_llm_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Some endpoints in use but no eval dataset evidence"}'
    )
    f = EvalBenchmarksCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Multiple endpoints compared"}'
    )
    f = EvalBenchmarksCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = EvalBenchmarksCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
