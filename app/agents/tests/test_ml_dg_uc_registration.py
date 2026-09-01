from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.dg_uc_registration import MlUcRegistrationCheck

_Q = Question(
    id="ML-DG-01",
    pillar_id="data-ai-governance",
    title="Register models and features in Unity Catalog",
    principle="Govern ML artifacts at the source",
)

# Needle "uc_ml_count" matches _UC_ML_SQL; "legacy_ml_count" matches _LEGACY_ML_SQL.
def _ctx(uc: int, legacy: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(
            {
                "uc_ml_count": [{"uc_ml_count": uc}],
                "legacy_ml_count": [{"legacy_ml_count": legacy}],
            }
        ),
        catalogs=["main"],
    )


def test_met_medium_confidence():
    f = MlUcRegistrationCheck().run(_Q, _ctx(90, 5))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM
    assert f.score is not None
    assert f.score > 0.80


def test_partial():
    f = MlUcRegistrationCheck().run(_Q, _ctx(60, 40))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.MEDIUM


def test_not_met():
    f = MlUcRegistrationCheck().run(_Q, _ctx(10, 90))
    assert f.verdict is Verdict.NOT_MET


def test_empty_is_unknown_low():
    f = MlUcRegistrationCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_collect_includes_note_evidence():
    ctx = _ctx(10, 2)
    evidence = MlUcRegistrationCheck().collect(ctx)
    assert len(evidence) == 2
    assert evidence[0].kind == "sql"
    assert evidence[1].kind == "note"
    assert "hive_metastore" in evidence[0].summary.lower()
    assert "proxy" in evidence[1].summary.lower() or "limitation" in evidence[1].summary.lower()


def test_score_is_ratio_of_uc_to_total():
    f = MlUcRegistrationCheck().run(_Q, _ctx(8, 2))
    # 8 / (8 + 2) = 0.8
    assert f.score == 0.8
