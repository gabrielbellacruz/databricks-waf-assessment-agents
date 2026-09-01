"""Automated experiment tracking check (LLM-judged).

Answers:
  ML-OE-02  Automate experiment tracking

Signal: ``system.access.audit`` for MLflow run creation and metric/parameter
logging events over the last 30 days. Automated pipelines that call MLflow
programmatically will generate consistent createRun, logMetric, and logParam
events; manual or ad-hoc work tends to produce sparse, user-driven bursts.

Two pieces of evidence:
1. Run creation and logging volume: total createRun events and log-type events
   (logMetric, logBatch, logParam) — high, regular volume suggests automation.
2. Distinct callers: how many users / service principals are generating run
   events. A single human user with sporadic activity suggests manual tracking;
   multiple service-principal callers or large volumes suggest automation.

Limitation: system.access.audit does not distinguish between interactive
notebook calls and fully automated CI/CD pipeline runs. Volume and diversity
of callers are proxies; whether training is triggered automatically as part of
a pipeline requires manual confirmation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_RUN_VOLUME_SQL = """\
SELECT action_name,
       COUNT(*) AS event_count
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND action_name IN (
    'createRun', 'updateRun', 'logMetric', 'logParam',
    'logBatch', 'logModel', 'setTag'
  )
GROUP BY action_name
ORDER BY event_count DESC\
"""

_CALLER_SQL = """\
SELECT COUNT(DISTINCT user_identity.email) AS distinct_callers,
       SUM(CASE WHEN user_identity.email NOT LIKE '%@%'
                THEN 1 ELSE 0 END) AS sp_events
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND action_name IN (
    'createRun', 'logMetric', 'logBatch', 'logParam', 'logModel'
  )\
"""

_NOTE = (
    "system.access.audit captures MLflow REST API calls but cannot distinguish "
    "automated pipeline calls from interactive notebook executions. High, consistent "
    "event volumes from service-principal identities are strong proxies for automation; "
    "sporadic user-email-based activity suggests manual tracking. A reviewer must confirm whether "
    "training pipelines log metrics automatically and whether experiment naming conventions "
    "enforce run reproducibility."
)

_REF = "https://docs.databricks.com/en/mlflow/tracking.html"


@register(layer="ml", question_ids=["ML-OE-02"])
class ExperimentTrackingCheck(Check):
    """Assess automated experiment tracking via MLflow run and metric audit events.

    Evidence:
    - system.access.audit: volume of createRun/logMetric/logBatch events by type.
    - system.access.audit: distinct callers and service-principal event share.
    A note records that automation vs manual cannot be confirmed from counts alone.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        run_rows = ctx.sql.query(_RUN_VOLUME_SQL)
        caller_rows = ctx.sql.query(_CALLER_SQL)

        total_events = sum(int(r.get("event_count") or 0) for r in run_rows)
        distinct_action_types = len(run_rows)

        if total_events > 0:
            run_summary = (
                f"{total_events} MLflow run/metric event(s) across "
                f"{distinct_action_types} action type(s) in the last 30 days"
            )
        else:
            run_summary = (
                "No MLflow run creation or metric logging events found in "
                "system.access.audit for the last 30 days"
            )

        run_evidence = Evidence(
            kind="sql",
            summary=run_summary,
            detail=_RUN_VOLUME_SQL,
            rows=run_rows,
            ref=_REF,
        )

        c = caller_rows[0] if caller_rows else {}
        distinct_callers = int(c.get("distinct_callers") or 0)
        sp_events = int(c.get("sp_events") or 0)

        caller_summary = (
            f"{distinct_callers} distinct caller(s) generated MLflow run events; "
            f"{sp_events} event(s) from service-principal identities "
            "(email without '@' = SP heuristic) in the last 30 days"
        )

        caller_evidence = Evidence(
            kind="sql",
            summary=caller_summary,
            detail=_CALLER_SQL,
            rows=[{"distinct_callers": distinct_callers, "sp_events": sp_events}],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [run_evidence, caller_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
