from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.co_schedule_efficiency import OrcScheduleEfficiencyCheck

_Q = Question(
    id="ORC-CO-03",
    pillar_id="cost-optimization",
    title="Right-time schedules to avoid unnecessary runs",
    principle="Optimize cost",
)

# Distinct needles:
#   "scheduled_jobs"  -> _SQL_TRIGGER (CASE WHEN trigger.periodic IS NOT NULL ... AS scheduled_jobs)
#   "distinct_jobs"   -> _SQL_RUNS    (COUNT(DISTINCT job_id) AS distinct_jobs)
_FAKE_SQL = {
    "scheduled_jobs": [
        {
            "total_jobs": 20,
            "continuous_jobs": 2,
            "scheduled_jobs": 12,
            "event_driven_jobs": 6,
        }
    ],
    "distinct_jobs": [
        {
            "total_runs": 300,
            "distinct_jobs": 18,
            "failed_runs": 30,
        }
    ],
}


def _ctx(llm_response: str | None = "") -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient(dict(_FAKE_SQL)),
        catalogs=["main"],
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_orchestration_co03_collect_three_evidences():
    ev = OrcScheduleEfficiencyCheck().collect(_ctx())
    assert len(ev) == 3


def test_orchestration_co03_collect_trigger_evidence():
    ev = OrcScheduleEfficiencyCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "20" in ev[0].summary  # total_jobs
    assert "12" in ev[0].summary  # scheduled_jobs
    assert ev[0].rows[0]["continuous_jobs"] == 2


def test_orchestration_co03_collect_run_evidence():
    ev = OrcScheduleEfficiencyCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    assert "300" in ev[1].summary  # total_runs
    assert ev[1].rows[0]["failed_runs"] == 30


def test_orchestration_co03_collect_note_evidence():
    ev = OrcScheduleEfficiencyCheck().collect(_ctx())
    assert ev[2].kind == "note"


def test_orchestration_co03_judge_maps_verdict_caps_confidence():
    resp = (
        '{"verdict": "partial", "confidence": "high",'
        ' "score": null, "rationale": "Some jobs over-scheduled"}'
    )
    f = OrcScheduleEfficiencyCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.PARTIAL
    # LLM confidence is capped at medium even if the model claims high
    assert f.confidence is Confidence.MEDIUM
    assert f.sources


def test_orchestration_co03_judge_not_met_verdict():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "Many always-on jobs with no justification"}'
    )
    f = OrcScheduleEfficiencyCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_orchestration_co03_no_llm_degrades_to_unassessed():
    f = OrcScheduleEfficiencyCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    # Evidence is still attached for explainability
    assert f.sources
