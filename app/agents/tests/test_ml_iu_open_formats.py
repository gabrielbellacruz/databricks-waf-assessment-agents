from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.iu_open_formats import MlOpenFormatsCheck

_Q = Question(
    id="ML-IU-01",
    pillar_id="interoperability-usability",
    title="Use open ML frameworks and formats",
    principle="Store ML artifacts in open, interoperable formats",
)

# Needle "data_source_format" → _FORMAT_SQL (returns both columns)
def _ctx(total: int, open_fmt: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="ml",
        sql=FakeSqlClient(
            {"data_source_format": [{"total_uc_tables": total, "open_format_tables": open_fmt}]}
        ),
        catalogs=["main"],
    )


def test_met_high_confidence():
    f = MlOpenFormatsCheck().run(_Q, _ctx(100, 90))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.9


def test_partial():
    f = MlOpenFormatsCheck().run(_Q, _ctx(100, 65))
    assert f.verdict is Verdict.PARTIAL


def test_not_met():
    f = MlOpenFormatsCheck().run(_Q, _ctx(100, 30))
    assert f.verdict is Verdict.NOT_MET


def test_empty_is_unknown_low():
    f = MlOpenFormatsCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_collect_includes_note_about_frameworks():
    ev = MlOpenFormatsCheck().collect(_ctx(50, 40))
    assert len(ev) == 2
    assert ev[1].kind == "note"
    assert "framework" in ev[1].summary.lower()


def test_score_precision():
    f = MlOpenFormatsCheck().run(_Q, _ctx(3, 2))
    # 2/3 ≈ 0.6667
    assert f.score == round(2 / 3, 4)
