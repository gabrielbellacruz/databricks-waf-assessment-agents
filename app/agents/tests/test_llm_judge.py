from __future__ import annotations

from waf_agents.core.clients import (
    AgentContext,
    ArchitectureContext,
    FakeLlmClient,
    FakeSqlClient,
)
from waf_agents.core.llm import _parse, build_user_prompt, judge_with_llm
from waf_agents.core.models import Confidence, Evidence, Question, Verdict

_Q = Question(id="ING-X", pillar_id="reliability", title="Some practice", principle="p")
_EV = [Evidence(kind="job_config", summary="3 jobs use retries", rows=[{"n": 3}])]


def _ctx(
    response: str | None, arch: ArchitectureContext | None = None
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient(),
        llm=FakeLlmClient(response) if response is not None else None,
        architecture=arch,
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


_OK = '{"verdict":"met","confidence":"medium","score":null,"rationale":"ok"}'


def test_architecture_text_is_appended_to_prompt():
    arch = ArchitectureContext(text="We use a medallion architecture with Auto Loader.")
    ctx = _ctx(_OK, arch=arch)
    judge_with_llm(ctx, _Q, _EV)
    _, user = ctx.llm.calls[0]
    assert "ARCHITECTURE DOCUMENTATION" in user
    assert "medallion architecture" in user


def test_architecture_images_are_passed_to_llm():
    arch = ArchitectureContext(images=[("image/png", b"\x89PNGfake")])
    ctx = _ctx(_OK, arch=arch)
    judge_with_llm(ctx, _Q, _EV)
    assert ctx.llm.image_calls[0] == [("image/png", b"\x89PNGfake")]
    # The text prompt also notes the attachment so a text-only endpoint knows.
    assert "diagram image(s) attached" in ctx.llm.calls[0][1]


def test_no_architecture_leaves_prompt_and_images_clean():
    ctx = _ctx(_OK)
    judge_with_llm(ctx, _Q, _EV)
    assert ctx.llm.image_calls[0] == []
    assert "ARCHITECTURE DOCUMENTATION" not in ctx.llm.calls[0][1]
    # No docs -> no architecture sources; workspace evidence is untouched.
    assert ctx and all(e.kind != "architecture_doc" for e in _EV)
    f = judge_with_llm(_ctx(_OK), _Q, _EV)
    assert f.sources == _EV


def test_prompt_names_sources_and_asks_for_references():
    arch = ArchitectureContext(
        text="We encrypt with customer-managed keys.",
        doc_names=["spec.pdf"],
        images=[("image/png", b"\x89PNG")],
        image_names=["diagram.png"],
    )
    ctx = _ctx(_OK, arch=arch)
    judge_with_llm(ctx, _Q, _EV)
    _, user = ctx.llm.calls[0]
    # Sources are named so the judge (and the reviewer) can reference them, and
    # the judge is explicitly asked for referenceable citations.
    assert "spec.pdf" in user and "diagram.png" in user
    assert "doc_references" in user


def test_architecture_marker_attached_even_without_citations():
    arch = ArchitectureContext(text="x", doc_names=["spec.pdf"])
    f = judge_with_llm(_ctx(_OK, arch=arch), _Q, _EV)
    assert _EV[0] in f.sources  # workspace evidence kept
    markers = [e for e in f.sources if e.kind == "architecture_doc"]
    assert len(markers) == 1 and "spec.pdf" in markers[0].summary


def test_citations_are_referenceable_to_the_source_document():
    reply = (
        '{"verdict":"met","confidence":"medium","score":null,'
        '"rationale":"CMK per the uploaded design",'
        '"doc_references":[{"document":"spec.pdf",'
        '"quote":"All storage uses customer-managed keys in eu-west-1"}]}'
    )
    arch = ArchitectureContext(
        text="All storage uses customer-managed keys in eu-west-1", doc_names=["spec.pdf"]
    )
    f = judge_with_llm(_ctx(reply, arch=arch), _Q, _EV)
    cites = [e for e in f.sources if e.kind == "architecture_doc" and e.ref]
    assert cites, "expected a referenceable citation"
    assert cites[0].ref == "spec.pdf"  # which document to open
    assert "customer-managed keys in eu-west-1" in cites[0].detail  # exact text to find


def test_unparseable_reply_still_records_docs_were_provided():
    arch = ArchitectureContext(text="x", doc_names=["spec.pdf"])
    f = judge_with_llm(_ctx("not json at all", arch=arch), _Q, _EV)
    assert f.verdict is Verdict.UNKNOWN
    assert any(e.kind == "architecture_doc" for e in f.sources)
