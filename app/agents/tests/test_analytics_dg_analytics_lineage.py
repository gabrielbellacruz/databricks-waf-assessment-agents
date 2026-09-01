from __future__ import annotations

from waf_agents.analytics.checks.dg_analytics_lineage import AnalyticsLineageCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-DG-04",
    pillar_id="data-ai-governance",
    title="Expose lineage from dashboards to sources",
    principle="Analytics consumers should be able to trace data back to its origin",
)

# Needles: 'tables_with_lineage' matches _LINEAGE_SQL,
#          'uc_table_count' matches _UC_TABLE_COUNT_SQL.
_FAKE_RESPONSES = {
    "tables_with_lineage": [{"tables_with_lineage": 42, "total_lineage_edges": 120}],
    "uc_table_count": [{"uc_table_count": 200}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_lineage_evidence():
    ev = AnalyticsLineageCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "42" in ev[0].summary
    assert "120" in ev[0].summary


def test_collect_coverage_evidence():
    ev = AnalyticsLineageCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "200" in ev[1].summary


def test_collect_limitation_evidence():
    ev = AnalyticsLineageCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[2].kind == "uc_metadata"
    assert "lineage" in ev[2].summary.lower()


def test_judge_met():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Lineage tracked for most tables"}'
    )
    f = AnalyticsLineageCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_unknown_when_no_lineage():
    resp = (
        '{"verdict": "unknown", "confidence": "low",'
        ' "score": null, "rationale": "No lineage data found"}'
    )
    f = AnalyticsLineageCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.UNKNOWN


def test_no_llm_degrades_to_unassessed():
    f = AnalyticsLineageCheck().run(_Q, _ctx(llm_response=None))
    assert f.auto_assessable is False
    assert f.sources
