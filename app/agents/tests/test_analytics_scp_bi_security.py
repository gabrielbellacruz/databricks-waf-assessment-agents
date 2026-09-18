from __future__ import annotations

from waf_agents.analytics.checks.scp_bi_security import BiSecurityCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-SCP-05",
    pillar_id="security-compliance-privacy",
    title="Secure BI connections and shared results",
    principle="Protect data in transit and at rest",
)

# Needles are distinct substrings of the two SQL strings:
#   "system.compute.warehouses" -> _WAREHOUSE_SQL (FROM system.compute.warehouses)
#   "createShare"               -> _SHARE_EVENTS_SQL (action_name IN ('createShare', ...))


def _ctx(
    *,
    wh_rows: list[dict] | None = None,
    share_rows: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    responses: dict[str, list[dict]] = {}
    if wh_rows is not None:
        responses["system.compute.warehouses"] = wh_rows
    if share_rows is not None:
        responses["createShare"] = share_rows
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(responses),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_shows_encrypted_warehouse_ratio():
    # TLS enforcement is derived from warehouse_type: SERVERLESS/PRO/REAL_TIME
    # enforce TLS; CLASSIC depends on network config.
    rows = [
        {"warehouse_type": "SERVERLESS", "warehouse_count": 3},
        {"warehouse_type": "CLASSIC", "warehouse_count": 1},
    ]
    ev = BiSecurityCheck().collect(_ctx(wh_rows=rows))
    assert ev[0].kind == "sql"
    assert "3 of 4" in ev[0].summary
    assert "75.0%" in ev[0].summary


def test_collect_pro_type_counts_as_encrypted():
    rows = [{"warehouse_type": "PRO", "warehouse_count": 2}]
    ev = BiSecurityCheck().collect(_ctx(wh_rows=rows))
    assert "2 of 2" in ev[0].summary


def test_collect_no_warehouses_shows_message():
    ev = BiSecurityCheck().collect(_ctx(wh_rows=[]))
    assert "No warehouses found" in ev[0].summary


def test_collect_sharing_events_shown():
    share_rows = [{"action_name": "createShare", "event_count": 5}]
    ev = BiSecurityCheck().collect(_ctx(share_rows=share_rows))
    assert "5 sharing-related audit event(s)" in ev[1].summary


def test_collect_no_sharing_events_shows_message():
    ev = BiSecurityCheck().collect(_ctx(share_rows=[]))
    assert "No sharing events" in ev[1].summary


def test_collect_includes_note_evidence():
    ev = BiSecurityCheck().collect(_ctx())
    kinds = [e.kind for e in ev]
    assert "note" in kinds


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "Some serverless warehouses but classic present"}'
    )
    rows = [
        {"warehouse_type": "SERVERLESS", "warehouse_count": 2},
        {"warehouse_type": "CLASSIC", "warehouse_count": 2},
    ]
    f = BiSecurityCheck().run(_Q, _ctx(wh_rows=rows, llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_high_confidence():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "All serverless"}'
    )
    f = BiSecurityCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_returns_unassessed_with_sources():
    f = BiSecurityCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
