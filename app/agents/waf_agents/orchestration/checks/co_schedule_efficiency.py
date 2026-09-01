"""Schedule efficiency check (LLM-judged).

Answers:
  ORC-CO-03  Right-time schedules to avoid unnecessary runs

Whether a schedule interval is "right-sized" for the workload it drives requires
organisational context the system tables don't encode.  Two observable proxies
are collected:

  1. Trigger-type distribution from ``system.lakeflow.jobs`` — how many jobs
     are always-on vs periodically scheduled vs event-driven vs manual.
  2. Recent run volume and failure rate from ``system.lakeflow.job_run_timeline``
     — a high run count relative to success rate may indicate over-scheduling.

The LLM judge weighs both signals and a caveat note, then returns a verdict
A reviewer can confirm or override.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_TRIGGER = (
    "SELECT COUNT(*) AS total_jobs, "
    "SUM(CASE WHEN trigger.continuous IS NOT NULL THEN 1 ELSE 0 END) AS continuous_jobs, "
    "SUM(CASE WHEN trigger.periodic IS NOT NULL THEN 1 ELSE 0 END) AS scheduled_jobs, "
    "SUM(CASE WHEN trigger.file_arrival IS NOT NULL THEN 1 ELSE 0 END) AS event_driven_jobs "
    "FROM system.lakeflow.jobs "
    "WHERE delete_time IS NULL"
)

_SQL_RUNS = (
    "SELECT COUNT(DISTINCT run_id) AS total_runs, "
    "COUNT(DISTINCT job_id) AS distinct_jobs, "
    "SUM(CASE WHEN result_state IN ('FAILED','ERROR','TIMED_OUT') THEN 1 ELSE 0 END) "
    "AS failed_runs "
    "FROM system.lakeflow.job_run_timeline "
    "WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS"
)

_NOTE = (
    "Whether a schedule interval is right-sized for its workload requires knowledge of "
    "business SLAs and data freshness requirements that are not recorded in system tables. "
    "Trigger-type distribution and failure rates are only indirect proxies — manual confirmation "
    "needed to assess whether always-on or high-frequency schedules are justified."
)

_REF = "https://docs.databricks.com/en/workflows/jobs/schedule.html"


@register(layer="orchestration", question_ids=["ORC-CO-03"])
class OrcScheduleEfficiencyCheck(Check):
    """LLM-judged check for ORC-CO-03: right-time workflow scheduling.

    Evidence collected:
      1. Trigger-type distribution from ``system.lakeflow.jobs`` (kind ``sql``).
      2. Recent run volume and failure rate from ``system.lakeflow.job_run_timeline``
         (kind ``sql``).
      3. Caveat note on the limits of platform-observable signals (kind ``note``).
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        # Evidence 1: trigger-type distribution
        trigger_rows = ctx.sql.query(_SQL_TRIGGER)
        trigger_row = trigger_rows[0] if trigger_rows else {}
        total_jobs = int(trigger_row.get("total_jobs") or 0)
        continuous = int(trigger_row.get("continuous_jobs") or 0)
        scheduled = int(trigger_row.get("scheduled_jobs") or 0)
        event_driven = int(trigger_row.get("event_driven_jobs") or 0)
        ev_trigger = Evidence(
            kind="sql",
            summary=(
                f"{total_jobs} active jobs: {continuous} always-on (continuous), "
                f"{scheduled} scheduled (periodic), {event_driven} event-driven (file arrival)"
            ),
            detail=_SQL_TRIGGER,
            rows=[
                {
                    "total_jobs": total_jobs,
                    "continuous_jobs": continuous,
                    "scheduled_jobs": scheduled,
                    "event_driven_jobs": event_driven,
                }
            ],
            ref=_REF,
        )

        # Evidence 2: run volume and failure rate
        run_rows = ctx.sql.query(_SQL_RUNS)
        run_row = run_rows[0] if run_rows else {}
        total_runs = int(run_row.get("total_runs") or 0)
        distinct_jobs = int(run_row.get("distinct_jobs") or 0)
        failed_runs = int(run_row.get("failed_runs") or 0)
        if total_runs > 0:
            failure_pct = round(100.0 * failed_runs / total_runs, 1)
            run_summary = (
                f"{total_runs} task runs across {distinct_jobs} jobs "
                f"in the last 30 days; {failed_runs} failed/errored/timed-out "
                f"({failure_pct}%)"
            )
        else:
            failure_pct = 0.0
            run_summary = (
                    "No job runs found in system.lakeflow.job_run_timeline "
                    "for the last 30 days"
                )
        ev_runs = Evidence(
            kind="sql",
            summary=run_summary,
            detail=_SQL_RUNS,
            rows=[
                {
                    "total_runs": total_runs,
                    "distinct_jobs": distinct_jobs,
                    "failed_runs": failed_runs,
                    "failure_pct": failure_pct,
                }
            ],
            ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
        )

        # Evidence 3: proxy-limitation note
        ev_note = Evidence(kind="note", summary=_NOTE, rows=[], ref=_REF)

        return [ev_trigger, ev_runs, ev_note]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
