from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.processing.checks.oe_env_isolation import EnvIsolationCheck

_Q = Question(
    id="PRO-OE-04",
    pillar_id="operational-excellence",
    title="Isolate dev, staging, and production for processing",
    principle="Separate environments to reduce blast radius",
)

_SCHEMA_RESPONSE = [
    {"total_schemas": 20, "dev_schemas": 3, "staging_schemas": 2, "prod_schemas": 5}
]
_CATALOG_RESPONSE = [
    {"total_catalogs": 6, "dev_catalogs": 1, "staging_catalogs": 1, "prod_catalogs": 1}
]


def _ctx(
    schema_row: list[dict] | None = None,
    catalog_row: list[dict] | None = None,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="processing",
        sql=FakeSqlClient({
            "schemata": schema_row if schema_row is not None else _SCHEMA_RESPONSE,
            "catalogs": catalog_row if catalog_row is not None else _CATALOG_RESPONSE,
        }),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_schema_evidence_summary():
    ev = EnvIsolationCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "10 of 20" in ev[0].summary  # 3 dev + 2 staging + 5 prod = 10


def test_collect_catalog_evidence_summary():
    ev = EnvIsolationCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "3 of 6" in ev[1].summary  # 1 + 1 + 1


def test_collect_returns_note_evidence():
    ev = EnvIsolationCheck().collect(_ctx())
    assert len(ev) == 3
    assert ev[2].kind == "note"
    assert "workspace" in ev[2].summary.lower()


def test_collect_no_schemas_handled():
    ev = EnvIsolationCheck().collect(_ctx(schema_row=[], catalog_row=[]))
    assert "0 of 0" in ev[0].summary


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "All three environment tiers are present"}'
    )
    f = EnvIsolationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET


def test_judge_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "low",'
        ' "score": null, "rationale": "Dev and prod found but no staging"}'
    )
    f = EnvIsolationCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.LOW


def test_no_llm_degrades_to_unassessed():
    f = EnvIsolationCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
