from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.pe_feature_store import MlFeatureStoreCheck

_Q = Question(
    id="ML-PE-03",
    pillar_id="performance-efficiency",
    title="Use the feature store to avoid recomputing features",
    principle="Design workloads for performance",
)

_SCHEMA_ROWS = [{"feature_schemas": 3}]
_TABLE_ROWS = [{"feature_tables": 12, "schemas_with_features": 3}]


def _ctx(*, schema_rows=None, table_rows=None, llm_response: str | None = "") -> AgentContext:
    responses = {
        "feature_schemas": schema_rows if schema_rows is not None else _SCHEMA_ROWS,
        "feature_tables": table_rows if table_rows is not None else _TABLE_ROWS,
    }
    return AgentContext(
        assessment_id="test-ml-pe03",
        layer="ml",
        sql=FakeSqlClient(responses),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_schema_count():
    ev = MlFeatureStoreCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "3" in ev[0].summary
    assert "schema" in ev[0].summary.lower()


def test_collect_table_count():
    ev = MlFeatureStoreCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "12" in ev[1].summary


def test_collect_no_feature_schemas():
    ev = MlFeatureStoreCheck().collect(_ctx(schema_rows=[{"feature_schemas": 0}]))
    assert "0" in ev[0].summary or "No schemas" in ev[0].summary


def test_collect_attaches_limitation_note():
    ev = MlFeatureStoreCheck().collect(_ctx())
    assert ev[2].kind == "note"
    assert "Feature Engineering" in ev[2].summary


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium", "score": null,'
        ' "rationale": "Feature tables found"}'
    )
    f = MlFeatureStoreCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_no_llm_degrades_to_unassessed():
    f = MlFeatureStoreCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
