from __future__ import annotations

from waf_agents.ai.checks.iu_open_standards import AiOpenStandardsCheck
from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="AI-IU-01",
    pillar_id="iu",
    title="Use open standards for AI workflows",
    principle="Adopt open AI frameworks to avoid vendor lock-in",
)

# Distinct needles:
#   "mlflow_audit_count" -> _AUDIT_SQL
#   "fmapi_dbus"         -> _BILLING_SQL
_FAKE = {
    "mlflow_audit_count": [{"mlflow_audit_count": 150, "mlflow_users": 7}],
    "fmapi_dbus": [{"fmapi_dbus": 8, "total_dbus": 42.5}],
}


def _ctx(*, llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient(dict(_FAKE)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_reports_mlflow_events():
    ev = AiOpenStandardsCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "150" in ev[0].summary
    assert "mlflow" in ev[0].summary.lower() or "event" in ev[0].summary.lower()


def test_collect_reports_fmapi_billing():
    ev = AiOpenStandardsCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "8" in ev[1].summary
    assert "42.50" in ev[1].summary


def test_collect_includes_standards_limitation():
    ev = AiOpenStandardsCheck().collect(_ctx())
    assert ev[2].kind == "uc_metadata"
    assert "framework" in ev[2].summary.lower() or "system table" in ev[2].summary.lower()


def test_collect_has_three_evidence_items():
    ev = AiOpenStandardsCheck().collect(_ctx())
    assert len(ev) == 3


def test_collect_rows_attached():
    ev = AiOpenStandardsCheck().collect(_ctx())
    assert ev[0].rows[0]["mlflow_audit_count"] == 150
    assert ev[1].rows[0]["fmapi_dbus"] == 8


def test_collect_empty_sql_returns_zeros():
    ctx = AgentContext(
        assessment_id="a1",
        layer="ai",
        sql=FakeSqlClient({}),
        catalogs=[],
        llm=FakeLlmClient(""),
    )
    ev = AiOpenStandardsCheck().collect(ctx)
    assert "0" in ev[0].summary


def test_judge_maps_partial_verdict():
    resp = (
        '{"verdict": "partial", "confidence": "medium",'
        ' "score": null, "rationale": "MLflow used but framework diversity unclear"}'
    )
    f = AiOpenStandardsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_high_to_medium():
    resp = (
        '{"verdict": "met", "confidence": "high",'
        ' "score": null, "rationale": "MLflow and FMAPI widely used"}'
    )
    f = AiOpenStandardsCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = AiOpenStandardsCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
