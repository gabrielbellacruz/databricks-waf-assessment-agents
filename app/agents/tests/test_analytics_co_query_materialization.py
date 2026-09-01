from __future__ import annotations

from waf_agents.analytics.checks.co_query_materialization import QueryMaterializationCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-CO-05",
    pillar_id="cost-optimization",
    title="Materialize expensive repeated queries",
    principle="Reduce redundant compute by pre-computing repeated results",
)

# Needles are distinct substrings of the two SQL strings:
#   "HAVING COUNT"           -> _SLOW_REPEATED_SQL (HAVING COUNT(*) >= 3)
#   "REFRESH MATERIALIZED"   -> _MV_REFRESH_SQL (ILIKE '%REFRESH MATERIALIZED VIEW%')
_REPEATED_ROWS = [
    {
        "query_text": "SELECT product_id, SUM(revenue) FROM orders GROUP BY 1",
        "execution_count": 15,
        "avg_duration_ms": 9200.0,
    },
    {
        "query_text": "SELECT region, COUNT(*) FROM events GROUP BY region",
        "execution_count": 8,
        "avg_duration_ms": 7500.0,
    },
]

_MV_ROWS = [{"refresh_count": 3}]


def _ctx(
    *,
    repeated_rows: list[dict] | None = None,
    mv_rows: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    responses: dict[str, list[dict]] = {}
    if repeated_rows is not None:
        responses["HAVING COUNT"] = repeated_rows
    if mv_rows is not None:
        responses["REFRESH MATERIALIZED"] = mv_rows
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(responses),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_repeated_queries_summary():
    ev = QueryMaterializationCheck().collect(_ctx(repeated_rows=_REPEATED_ROWS))
    assert ev[0].kind == "sql"
    assert "2 repeated expensive SELECT pattern(s)" in ev[0].summary
    assert len(ev[0].rows) == 2


def test_collect_mv_refresh_count():
    ev = QueryMaterializationCheck().collect(
        _ctx(repeated_rows=_REPEATED_ROWS, mv_rows=_MV_ROWS)
    )
    assert ev[1].kind == "sql"
    assert "3 REFRESH MATERIALIZED VIEW" in ev[1].summary
    assert ev[1].rows[0]["refresh_count"] == 3


def test_collect_no_repeated_queries_summary():
    ev = QueryMaterializationCheck().collect(_ctx(repeated_rows=[]))
    assert "No repeated expensive" in ev[0].summary


def test_judge_verdict_and_confidence_cap():
    resp = (
        '{"verdict": "not_met", "confidence": "high", "score": null,'
        ' "rationale": "Many repeated expensive queries with no materialized views found"}'
    )
    f = QueryMaterializationCheck().run(
        _Q, _ctx(repeated_rows=_REPEATED_ROWS, llm_response=resp)
    )
    assert f.verdict is Verdict.NOT_MET
    # LLM confidence capped at medium even if it claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_no_llm_is_unassessed_with_sources():
    f = QueryMaterializationCheck().run(
        _Q, _ctx(repeated_rows=_REPEATED_ROWS, llm_response=None)
    )
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
