from __future__ import annotations

from waf_agents.ai.checks.pe_model_rightsizing import ModelRightsizingCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-PE-04",
    pillar_id="pe",
    title="Right-size the model to the task",
    principle="Match model capability and cost to the complexity of each AI task",
)

# Two distinct needles for two SQL queries in this check:
#   "avg_tokens_per_request"  -> token usage query (endpoint_usage)
#   "gpu_sku_dbus"            -> GPU billing query (billing.usage)
_FAKE = {
    "avg_tokens_per_request": [
        {
            "served_entity_name": "llama-3-70b-instruct",
            "request_count": 3000,
            "avg_tokens_per_request": 1200.0,
            "avg_latency_ms": 600.0,
        },
        {
            "served_entity_name": "llama-3-8b-instruct",
            "request_count": 8000,
            "avg_tokens_per_request": 150.0,
            "avg_latency_ms": 80.0,
        },
    ],
    "gpu_sku_dbus": [
        {"sku_name": "INFERENCE_SERVING_GPU_LARGE", "gpu_sku_dbus": 450.0},
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def _ctx_empty(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_token_evidence():
    ev = ModelRightsizingCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "2 served entity type(s)" in ev[0].summary
    assert "llama-3-70b-instruct" in ev[0].summary


def test_collect_gpu_evidence():
    ev = ModelRightsizingCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "GPU" in ev[1].summary
    assert "450.00" in ev[1].summary


def test_collect_note_evidence():
    ev = ModelRightsizingCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[2].kind == "note"
    note_text = ev[2].summary.lower()
    assert "right-sizing" in note_text or "right-size" in note_text or "task" in note_text


def test_collect_token_rows():
    ev = ModelRightsizingCheck().collect(_ctx())
    assert len(ev[0].rows) == 2
    assert ev[0].rows[0]["avg_tokens_per_request"] == 1200.0


def test_collect_gpu_rows():
    ev = ModelRightsizingCheck().collect(_ctx())
    assert ev[1].rows[0]["gpu_sku_dbus"] == 450.0


def test_collect_empty_no_crash():
    ev = ModelRightsizingCheck().collect(_ctx_empty())
    assert "No serving endpoint requests" in ev[0].summary
    assert "No GPU billing" in ev[1].summary


def test_judge_maps_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "low",'
        ' "score": null, "rationale": "Large model used for low-token tasks"}'
    )
    f = ModelRightsizingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.sources


def test_judge_caps_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Models appropriately sized"}'
    )
    f = ModelRightsizingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = ModelRightsizingCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
