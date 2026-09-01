from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ingestion.checks.data_quality_standards import DataQualityStandardsCheck

_Q = Question(
    id="ING-DG-05",
    pillar_id="governance",
    title="Define data quality standards for incoming data",
    principle="Govern data quality at the point of ingestion",
)

_LLM_PARTIAL = (
    '{"verdict": "partial", "confidence": "medium", "score": null,'
    ' "rationale": "Some constraints exist but coverage is low relative to governed tables."}'
)
_LLM_NOT_MET = (
    '{"verdict": "not_met", "confidence": "low", "score": null,'
    ' "rationale": "No constraints found; manual confirmation needed."}'
)


def _ctx(
    *,
    llm_response: str | None = _LLM_PARTIAL,
    check_count: int = 5,
    table_count: int = 12,
    total_tables: int = 100,
) -> AgentContext:
    return AgentContext(
        assessment_id="test-dq-standards",
        layer="ingestion",
        sql=FakeSqlClient(
            {
                "check_constraints": [{"check_constraints": check_count}],
                "table_constraints": [{"table_constraints": table_count}],
                "information_schema.tables": [{"total_tables": total_tables}],
            }
        ),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


# ---------------------------------------------------------------------------
# collect() — evidence shape
# ---------------------------------------------------------------------------


def test_collect_returns_two_evidence_entries():
    ev = DataQualityStandardsCheck().collect(_ctx())
    assert len(ev) == 2


def test_collect_sql_evidence_kind_and_counts():
    ev = DataQualityStandardsCheck().collect(_ctx())
    sql_ev = ev[0]
    assert sql_ev.kind == "sql"
    assert "5" in sql_ev.summary
    assert "12" in sql_ev.summary
    assert "100" in sql_ev.summary
    assert sql_ev.rows[0]["check_constraints"] == 5
    assert sql_ev.rows[0]["table_constraints"] == 12
    assert sql_ev.rows[0]["total_tables"] == 100


def test_collect_sql_evidence_ref():
    ev = DataQualityStandardsCheck().collect(_ctx())
    assert ev[0].ref == "https://docs.databricks.com/en/tables/constraints.html"


def test_collect_note_evidence_kind_and_no_rows():
    ev = DataQualityStandardsCheck().collect(_ctx())
    note_ev = ev[1]
    assert note_ev.kind == "note"
    assert note_ev.rows == []
    assert note_ev.ref == "https://docs.databricks.com/en/tables/constraints.html"


def test_collect_note_mentions_dlt_and_sa_confirmation():
    ev = DataQualityStandardsCheck().collect(_ctx())
    note_summary = ev[1].summary
    assert "DLT" in note_summary or "Lakeflow" in note_summary
    assert "manual confirmation" in note_summary


def test_collect_zero_constraints_handled():
    ev = DataQualityStandardsCheck().collect(
        _ctx(check_count=0, table_count=0, total_tables=0)
    )
    assert ev[0].rows[0]["check_constraints"] == 0
    assert ev[0].rows[0]["table_constraints"] == 0
    assert ev[0].rows[0]["total_tables"] == 0


def test_collect_empty_sql_responses_handled():
    """FakeSqlClient with no matching needles returns []; must not raise."""
    ctx = AgentContext(
        assessment_id="t-empty",
        layer="ingestion",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=None,
    )
    ev = DataQualityStandardsCheck().collect(ctx)
    assert ev[0].rows[0]["check_constraints"] == 0
    assert ev[0].rows[0]["table_constraints"] == 0
    assert ev[0].rows[0]["total_tables"] == 0


# ---------------------------------------------------------------------------
# judge() — LLM verdict mapping
# ---------------------------------------------------------------------------


def test_judge_partial_verdict_mapped():
    f = DataQualityStandardsCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_judge_not_met_verdict_mapped():
    f = DataQualityStandardsCheck().run(_Q, _ctx(llm_response=_LLM_NOT_MET))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.LOW


def test_judge_confidence_capped_at_medium_when_llm_claims_high():
    high_conf = (
        '{"verdict": "met", "confidence": "high", "score": null,'
        ' "rationale": "Comprehensive constraints in place."}'
    )
    f = DataQualityStandardsCheck().run(_Q, _ctx(llm_response=high_conf))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_sources_include_sql_and_note():
    f = DataQualityStandardsCheck().run(_Q, _ctx(llm_response=_LLM_PARTIAL))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


# ---------------------------------------------------------------------------
# llm=None — degrades to unassessed
# ---------------------------------------------------------------------------


def test_no_llm_degrades_to_unassessed():
    f = DataQualityStandardsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources  # evidence still attached even without LLM
