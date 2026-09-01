from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.scp_service_principal import MlServicePrincipalCheck

_Q = Question(
    id="ML-SCP-01",
    pillar_id="security-compliance-privacy",
    title="Run training and serving as service principals",
    principle="Secure ML workload identity",
)


def _ctx(total: int, sp_jobs: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(
            {"system.lakeflow.jobs": [{"total": total, "sp_jobs": sp_jobs}]}
        ),
        catalogs=["main"],
    )


# ---------------------------------------------------------------------------
# Deterministic thresholding
# ---------------------------------------------------------------------------


def test_met_medium_confidence():
    f = MlServicePrincipalCheck().run(_Q, _ctx(100, 92))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score == 0.92


def test_partial():
    f = MlServicePrincipalCheck().run(_Q, _ctx(100, 60))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_not_met():
    f = MlServicePrincipalCheck().run(_Q, _ctx(100, 10))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_no_jobs_is_unknown_low():
    f = MlServicePrincipalCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_score_rounded_to_four_decimal_places():
    f = MlServicePrincipalCheck().run(_Q, _ctx(3, 2))
    # 2/3 = 0.6667
    assert f.score is not None
    assert f.score == round(2 / 3, 4)


def test_sources_include_job_evidence_and_note():
    f = MlServicePrincipalCheck().run(_Q, _ctx(50, 48))
    kinds = [e.kind for e in f.sources]
    assert "sql" in kinds
    assert "note" in kinds


def test_sql_evidence_row_values():
    f = MlServicePrincipalCheck().run(_Q, _ctx(50, 45))
    sql_ev = next(e for e in f.sources if e.kind == "sql")
    assert sql_ev.rows[0]["total"] == 50
    assert sql_ev.rows[0]["sp_jobs"] == 45


def test_note_mentions_serving_endpoint():
    f = MlServicePrincipalCheck().run(_Q, _ctx(50, 45))
    note_ev = next(e for e in f.sources if e.kind == "note")
    assert "serving" in note_ev.summary.lower() or "endpoint" in note_ev.summary.lower()
