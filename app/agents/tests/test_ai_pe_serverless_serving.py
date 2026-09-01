from __future__ import annotations

from waf_agents.ai.checks.pe_serverless_serving import ServerlessServingCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-PE-01",
    pillar_id="pe",
    title="Use serverless serving for elastic AI performance",
    principle="Prefer pay-per-token serverless endpoints for bursty AI workloads",
)

# Needle: "total_serving_dbus" — unique alias in the billing SERVING SKU SQL
_FAKE_MIXED = {
    "total_serving_dbus": [
        {"total_serving_dbus": 100.0, "gpu_dbus": 80.0, "distinct_sku_count": 3}
    ]
}

_FAKE_SERVERLESS = {
    "total_serving_dbus": [
        {"total_serving_dbus": 50.0, "gpu_dbus": 5.0, "distinct_sku_count": 2}
    ]
}


def _ctx(fake: dict, *, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(fake),
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


def test_collect_reports_total_dbus():
    ev = ServerlessServingCheck().collect(_ctx(_FAKE_MIXED))
    assert ev[0].kind == "sql"
    assert "100.00 total serving DBUs" in ev[0].summary


def test_collect_reports_gpu_pct():
    ev = ServerlessServingCheck().collect(_ctx(_FAKE_MIXED))
    assert "80.0%" in ev[0].summary or "80%" in ev[0].summary


def test_collect_reports_sku_count():
    ev = ServerlessServingCheck().collect(_ctx(_FAKE_MIXED))
    assert "3 distinct serving SKU(s)" in ev[0].summary


def test_collect_has_rows():
    ev = ServerlessServingCheck().collect(_ctx(_FAKE_MIXED))
    assert ev[0].rows[0]["total_serving_dbus"] == 100.0


def test_collect_note_evidence():
    ev = ServerlessServingCheck().collect(_ctx(_FAKE_MIXED))
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "serverless" in ev[1].summary.lower()


def test_collect_empty_no_crash():
    ev = ServerlessServingCheck().collect(_ctx_empty())
    assert "No serving/inference billing usage" in ev[0].summary


def test_judge_maps_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium", "score": null,'
        ' "rationale": "High GPU share suggests provisioned throughput"}'
    )
    f = ServerlessServingCheck().run(_Q, _ctx(_FAKE_MIXED, llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.sources


def test_judge_caps_confidence():
    resp = (
        '{"verdict": "not_met", "confidence": "high",'
        ' "score": null, "rationale": "All GPU spend"}'
    )
    f = ServerlessServingCheck().run(_Q, _ctx(_FAKE_MIXED, llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = ServerlessServingCheck().run(_Q, _ctx(_FAKE_MIXED, llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
