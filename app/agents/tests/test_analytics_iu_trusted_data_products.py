from __future__ import annotations

from waf_agents.analytics.checks.iu_trusted_data_products import TrustedDataProductsCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-IU-02",
    pillar_id="interoperability-usability",
    title="Publish analytics data products the business trusts",
    principle="Analytics outputs should be certified, documented, and discoverable",
)

# Needles: 'described_tables' matches _DESCRIBED_TABLES_SQL,
#          'curated_schemas' matches _CURATED_SCHEMAS_SQL,
#          'certified_tables' matches _CERTIFIED_TAGS_SQL.
_FAKE_RESPONSES = {
    "described_tables": [{"total_tables": 100, "described_tables": 65}],
    "curated_schemas": [{"curated_schemas": 4, "curated_tables": 30}],
    "certified_tables": [{"certified_tables": 12}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(dict(_FAKE_RESPONSES)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_description_evidence():
    ev = TrustedDataProductsCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "65 of 100" in ev[0].summary
    assert "65.0%" in ev[0].summary


def test_collect_curated_evidence():
    ev = TrustedDataProductsCheck().collect(_ctx())
    assert "30" in ev[1].summary
    assert "4" in ev[1].summary


def test_collect_certified_tag_evidence():
    ev = TrustedDataProductsCheck().collect(_ctx())
    assert len(ev) == 3
    assert "12" in ev[2].summary
    assert "certified" in ev[2].summary.lower()


def test_judge_met():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "Well-documented certified data products exist"}'
    )
    f = TrustedDataProductsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET


def test_judge_partial_confidence_capped():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some certified tables but incomplete"}'
    )
    f = TrustedDataProductsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = TrustedDataProductsCheck().run(_Q, _ctx(llm_response=None))
    assert f.auto_assessable is False
    assert f.sources
