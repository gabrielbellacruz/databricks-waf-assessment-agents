from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.iu_feature_store import MlFeatureStoreCheck

_Q = Question(
    id="ML-IU-02",
    pillar_id="interoperability-usability",
    title="Share reusable features via a feature store",
    principle="Centralise features for reuse across ML models",
)

# Needle "feature_tables" → _FEATURE_TABLES_SQL
# Needle "total_uc_tables"→ _TOTAL_UC_SQL
def _ctx(feature: int, total: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(
            {
                "feature_tables": [{"feature_tables": feature}],
                "total_uc_tables": [{"total_uc_tables": total}],
            }
        ),
        catalogs=["main"],
    )


def test_met_medium_confidence():
    # 15 / 200 = 7.5% >= 5% threshold
    f = MlFeatureStoreCheck().run(_Q, _ctx(15, 200))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_partial():
    # 1 / 200 = 0.5% >= 0.5% threshold
    f = MlFeatureStoreCheck().run(_Q, _ctx(1, 200))
    assert f.verdict is Verdict.PARTIAL


def test_not_met():
    f = MlFeatureStoreCheck().run(_Q, _ctx(0, 200))
    assert f.verdict is Verdict.NOT_MET


def test_empty_uc_is_unknown_low():
    f = MlFeatureStoreCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_collect_summary_mentions_schemas():
    ev = MlFeatureStoreCheck().collect(_ctx(5, 100))
    assert len(ev) == 1
    assert ev[0].kind == "sql"
    assert "5" in ev[0].summary


def test_score_is_ratio():
    f = MlFeatureStoreCheck().run(_Q, _ctx(10, 100))
    assert f.score == 0.1
