from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.oe_event_driven import EventDrivenTriggeringCheck

_Q = Question(
    id="ORC-OE-01",
    pillar_id="oe",
    title="Use automated, event-driven triggering",
    principle="Automate workflow execution rather than relying on manual triggers",
)


def _ctx(total: int, scheduled: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient(
            {"schedule IS NOT NULL": [{"total": total, "scheduled_jobs": scheduled}]}
        ),
        catalogs=[],
    )


def test_met_high_confidence():
    f = EventDrivenTriggeringCheck().run(_Q, _ctx(100, 85))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.85
    assert f.sources and f.sources[0].kind == "sql"


def test_partial():
    f = EventDrivenTriggeringCheck().run(_Q, _ctx(100, 60))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.60


def test_not_met():
    f = EventDrivenTriggeringCheck().run(_Q, _ctx(100, 20))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.HIGH


def test_empty_is_unknown_low():
    f = EventDrivenTriggeringCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_score_rounds_to_four_places():
    f = EventDrivenTriggeringCheck().run(_Q, _ctx(3, 2))
    # 2/3 = 0.6667
    assert f.score == round(2 / 3, 4)


def test_evidence_contains_row_data():
    f = EventDrivenTriggeringCheck().run(_Q, _ctx(50, 40))
    row = f.sources[0].rows[0]
    assert row["total"] == 50
    assert row["scheduled_jobs"] == 40
