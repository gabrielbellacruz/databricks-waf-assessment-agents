from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.llm import _parse, build_user_prompt, judge_with_llm
from waf_agents.core.models import Confidence, Evidence, Question, Verdict

_Q = Question(id="ING-X", pillar_id="reliability", title="Some practice", principle="p")
_EV = [Evidence(kind="job_config", summary="3 jobs use retries", rows=[{"n": 3}])]


def _ctx(response: str | None) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient(),
        llm=FakeLlmClient(response) if response is not None else None,
    )


def test_parse_plain_and_fenced_and_garbage():
    assert _parse('{"verdict":"met"}')["verdict"] == "met"
    assert _parse('```json\n{"verdict":"met"}\n```')["verdict"] == "met"
    assert _parse("here you go: {\"verdict\":\"partial\"} ok")["verdict"] == "partial"
    assert _parse("not json at all") is None


def test_prompt_includes_question_and_evidence():
    p = build_user_prompt(_Q, _EV)
    assert "ING-X" in p and "3 jobs use retries" in p


def test_judge_maps_and_attaches_evidence():
    f = judge_with_llm(
        _ctx('{"verdict":"met","confidence":"medium","score":null,"rationale":"ok"}'), _Q, _EV
    )
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources == _EV


def test_judge_unparseable_is_unknown_low():
    f = judge_with_llm(_ctx("sorry I cannot"), _Q, _EV)
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW
    assert f.auto_assessable is False


def test_judge_without_llm_is_unassessed():
    f = judge_with_llm(_ctx(None), _Q, _EV)
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False


def test_invalid_verdict_falls_back_to_unknown():
    f = judge_with_llm(_ctx('{"verdict":"definitely","confidence":"medium"}'), _Q, _EV)
    assert f.verdict is Verdict.UNKNOWN
