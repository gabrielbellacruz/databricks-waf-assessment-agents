from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.pe_representative_data import MlRepresentativeDataCheck

_Q = Question(
    id="ML-PE-04",
    pillar_id="performance-efficiency",
    title="Test model performance on representative data",
    principle="Run performance testing",
)

_ENDPOINT_ROWS = [
    {
        "endpoint_name": "classifier-v1",
        "request_count": 1000,
        "avg_latency_ms": 38.5,
        "p50_latency_ms": 30.0,
        "p95_latency_ms": 90.0,
        "p99_latency_ms": 150.0,
    }
]


def _ctx(*, endpoint_rows=None, llm_response: str | None = "") -> AgentContext:
    rows = endpoint_rows if endpoint_rows is not None else _ENDPOINT_ROWS
    return AgentContext(
        assessment_id="test-ml-pe04",
        layer="ml",
        sql=FakeSqlClient({"p95_latency_ms": rows}),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_summarises_endpoint_traffic():
    ev = MlRepresentativeDataCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "1" in ev[0].summary  # 1 endpoint
    assert "1,000" in ev[0].summary or "1000" in ev[0].summary


def test_collect_no_traffic():
    ev = MlRepresentativeDataCheck().collect(_ctx(endpoint_rows=[]))
    assert "No serving endpoint traffic" in ev[0].summary


def test_collect_attaches_note_evidence():
    ev = MlRepresentativeDataCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "representative" in ev[1].summary.lower()


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "low", "score": null,'
        ' "rationale": "Traffic exists but no test harness evidence"}'
    )
    f = MlRepresentativeDataCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL


def test_judge_caps_confidence():
    resp = '{"verdict": "met", "confidence": "high", "score": null, "rationale": "Traffic present"}'
    f = MlRepresentativeDataCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = MlRepresentativeDataCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
