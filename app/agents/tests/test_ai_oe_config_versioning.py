from __future__ import annotations

from waf_agents.ai.checks.oe_config_versioning import ConfigVersioningCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-OE-04",
    pillar_id="oe",
    title="Version prompts, models, and app configs together",
    principle="Treat AI configurations as versioned artefacts",
)

# Needles:
#   "createServingEndpoint" appears in _ENDPOINT_UPDATES_SQL action_name list
#   "DISTINCT endpoint_name" appears in _ENDPOINT_NAMES_SQL
_FAKE = {
    "createServingEndpoint": [
        {"action_name": "createServingEndpoint", "event_count": 5},
        {"action_name": "updateServingEndpoint", "event_count": 12},
    ],
    "DISTINCT endpoint_name": [
        {"endpoint_name": "chat-v1"},
        {"endpoint_name": "chat-v2"},
        {"endpoint_name": "embeddings-prod"},
    ],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_update_events_summary():
    ev = ConfigVersioningCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    # 5 + 12 = 17 total events
    assert "17" in ev[0].summary
    assert "2" in ev[0].summary  # 2 distinct action types


def test_collect_endpoint_names_version_heuristic():
    ev = ConfigVersioningCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "3 distinct endpoint" in ev[1].summary
    # chat-v1, chat-v2, embeddings-prod all match version tokens
    assert "2" in ev[1].summary or "3" in ev[1].summary


def test_collect_note_evidence():
    ev = ConfigVersioningCheck().collect(_ctx())
    assert ev[2].kind == "note"
    assert "NOT observable" in ev[2].summary


def test_collect_no_events():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        llm=FakeLlmClient(""),
    )
    ev = ConfigVersioningCheck().collect(ctx)
    assert "No serving endpoint" in ev[0].summary or "No" in ev[0].summary


def test_judge_not_met():
    resp = (
        '{"verdict": "not_met", "confidence": "low",'
        ' "score": null, "rationale": "No unified versioning workflow observed"}'
    )
    f = ConfigVersioningCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.LOW


def test_judge_met_capped_at_medium():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "Version tokens in endpoint names"}'
    )
    f = ConfigVersioningCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = ConfigVersioningCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
