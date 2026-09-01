from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.storage.checks.secure_sharing import SecureSharingCheck

_Q = Question(
    id="STO-IU-02",
    pillar_id="interoperability-usability",
    title="Enable secure sharing of stored data",
    principle="Share data securely across domain and organisational boundaries",
)

# Needle: "sharing_tables" matches the AS alias in _SHARING_TABLES_SQL and nowhere else.
_FAKE_RESPONSES = {
    "sharing_tables": [{"sharing_tables": 12, "sharing_catalogs": 3}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="storage",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_consumer_tables():
    ev = SecureSharingCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "12 DELTASHARING consumer table" in ev[0].summary
    assert "3 catalog" in ev[0].summary


def test_collect_limitation_note():
    ev = SecureSharingCheck().collect(_ctx())
    assert len(ev) == 2
    assert ev[1].kind == "uc_metadata"
    assert "Provider-side" in ev[1].summary


def test_collect_rows_attached():
    ev = SecureSharingCheck().collect(_ctx())
    assert any(r.get("sharing_tables") == 12 for r in ev[0].rows)


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Delta Sharing tables found across catalogs"}'
    )
    f = SecureSharingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some sharing in use"}'
    )
    f = SecureSharingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = SecureSharingCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
