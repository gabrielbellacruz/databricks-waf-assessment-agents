from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.rescue_invalid_data import RescueInvalidDataCheck

_Q = Question(
    id="ING-R-01",
    pillar_id="reliability",
    title="Automatically rescue invalid or nonconforming incoming data",
    principle="Handle data quality failures at the source rather than silently dropping records",
)


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    sql = FakeSqlClient(
        {
            "_rescued_data": [{"tables_with_rescue": 5}],
            "information_schema.tables": [{"total_tables": 20}],
        }
    )
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=sql,
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_evidence_reflects_counts():
    ev = RescueInvalidDataCheck().collect(_ctx())
    assert len(ev) == 1
    assert ev[0].kind == "sql"
    assert "5" in ev[0].summary
    assert "20" in ev[0].summary
    assert ev[0].rows == [{"tables_with_rescue": 5, "total_tables": 20}]
    assert ev[0].ref is not None and "rescue" in ev[0].ref


def test_judge_maps_llm_verdict_and_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high", '
        '"score": null, "rationale": "5/20 tables carry rescue column"}'
    )
    f = RescueInvalidDataCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM claimed high confidence; must be capped at medium
    assert f.confidence is Confidence.MEDIUM
    assert f.sources  # evidence attached for explainability


def test_no_llm_degrades_to_unassessed():
    f = RescueInvalidDataCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached even without a judge
