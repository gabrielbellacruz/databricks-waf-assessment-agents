from __future__ import annotations

from waf_agents.analytics.checks.scp_audit_coverage import QueryAuditCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-SCP-04",
    pillar_id="security-compliance-privacy",
    title="Audit analytics access and queries",
    principle="Monitor system security",
)

# Needles are distinct substrings of the two SQL strings:
#   "executed_by"  -> _QUERY_HISTORY_SQL (COUNT(DISTINCT executed_by))
#   "access.audit" -> _AUDIT_EVENTS_SQL  (FROM system.access.audit)


def _ctx(
    *,
    qh_rows: list[dict] | None = None,
    ae_rows: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    responses: dict[str, list[dict]] = {}
    if qh_rows is not None:
        responses["executed_by"] = qh_rows
    if ae_rows is not None:
        responses["access.audit"] = ae_rows
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(responses),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_shows_query_history_summary():
    ev = QueryAuditCheck().collect(
        _ctx(qh_rows=[{"total_queries": 500, "distinct_users": 10, "failed_queries": 5}])
    )
    assert ev[0].kind == "sql"
    assert "500 queries" in ev[0].summary
    assert "10 distinct user(s)" in ev[0].summary


def test_collect_shows_audit_event_summary():
    ev = QueryAuditCheck().collect(
        _ctx(ae_rows=[{"audit_event_count": 200, "distinct_users_audited": 8}])
    )
    assert ev[1].kind == "sql"
    assert "200 query-related audit event(s)" in ev[1].summary
    assert "8 user(s)" in ev[1].summary


def test_collect_includes_note_evidence():
    ev = QueryAuditCheck().collect(_ctx())
    kinds = [e.kind for e in ev]
    assert "note" in kinds


def test_collect_evidence_has_rows():
    ev = QueryAuditCheck().collect(
        _ctx(
            qh_rows=[{"total_queries": 100, "distinct_users": 5, "failed_queries": 2}],
            ae_rows=[{"audit_event_count": 50, "distinct_users_audited": 4}],
        )
    )
    assert any(r.get("total_queries") == 100 for r in ev[0].rows)
    assert any(r.get("audit_event_count") == 50 for r in ev[1].rows)


def test_collect_empty_returns_zero_counts():
    ev = QueryAuditCheck().collect(_ctx(qh_rows=[], ae_rows=[]))
    assert any(r.get("total_queries") == 0 for r in ev[0].rows)
    assert any(r.get("audit_event_count") == 0 for r in ev[1].rows)


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Strong audit trail in both tables"}'
    )
    f = QueryAuditCheck().run(
        _Q,
        _ctx(
            qh_rows=[{"total_queries": 1000, "distinct_users": 20, "failed_queries": 10}],
            ae_rows=[{"audit_event_count": 800, "distinct_users_audited": 18}],
            llm_response=resp,
        ),
    )
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "low",'
        ' "score": null, "rationale": "No audit events found"}'
    )
    f = QueryAuditCheck().run(_Q, _ctx(qh_rows=[], ae_rows=[], llm_response=resp))
    assert f.verdict is Verdict.NOT_MET


def test_no_llm_returns_unassessed_with_sources():
    f = QueryAuditCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
