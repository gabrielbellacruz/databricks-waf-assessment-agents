"""Enterprise scheduler integration check (LLM-judged).

Answers:
  ORC-IU-05  Integrate workflows with enterprise schedulers

Whether Databricks workflows are integrated with external enterprise schedulers
(Apache Airflow, Control-M, Autosys, Azure Data Factory, etc.) is not directly
visible in system tables — the scheduler calls the Databricks REST API from
outside the platform.

Two platform-side proxy signals are gathered via ``ctx.sql``:
  1. The mix of trigger types across active jobs — CRON/scheduled, file-arrival,
     and periodic — from ``system.lakeflow.jobs``.  Jobs driven purely by
     internal CRON schedules suggest scheduling is self-contained in Databricks,
     while jobs with no Databricks-side schedule may be triggered externally.
  2. The share of jobs with no schedule *and* no file-arrival trigger set:
     un-scheduled jobs that still have run history are good candidates for
     external-scheduler integration (they accept ad-hoc API calls).

A note Evidence records that external scheduling is architecturally invisible
from within the platform.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_TRIGGERS = (
    "SELECT COUNT(*) AS total_jobs, "
    "SUM(CASE WHEN schedule IS NOT NULL THEN 1 ELSE 0 END) AS cron_scheduled, "
    "SUM(CASE WHEN trigger.file_arrival IS NOT NULL THEN 1 ELSE 0 END) AS file_arrival_triggered, "
    "SUM(CASE WHEN trigger.periodic IS NOT NULL THEN 1 ELSE 0 END) AS periodic_triggered, "
    "SUM(CASE WHEN schedule IS NULL AND trigger.file_arrival IS NULL "
    "         AND trigger.periodic IS NULL THEN 1 ELSE 0 END) AS unscheduled_jobs "
    "FROM system.lakeflow.jobs "
    "WHERE delete_time IS NULL"
)

_SQL_EXTERNAL_CANDIDATES = (
    "SELECT COUNT(DISTINCT j.job_id) AS external_scheduler_candidates "
    "FROM system.lakeflow.jobs j "
    "INNER JOIN ("
    "SELECT DISTINCT job_id FROM system.lakeflow.job_run_timeline "
    "WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS"
    ") r ON j.job_id = r.job_id "
    "WHERE j.delete_time IS NULL "
    "AND j.schedule IS NULL "
    "AND j.trigger.file_arrival IS NULL"
)

_NOTE_SUMMARY = (
    "Integration with external enterprise schedulers (Airflow, Control-M, Autosys, "
    "ADF, etc.) is architecturally invisible from within Databricks: the external tool "
    "calls the Jobs REST API, leaving no internal signal beyond run history. "
    "Un-scheduled jobs with recent runs are the closest observable proxy. "
    "Manual confirmation and external scheduler configuration review needed."
)

_REF = "https://docs.databricks.com/en/workflows/jobs/jobs-2.0-api.html"


@register(layer="orchestration", question_ids=["ORC-IU-05"])
class SchedulerIntegrationCheck(Check):
    """LLM-judged check for ORC-IU-05: enterprise scheduler integration.

    Evidence collected:
      1. Trigger-type breakdown for active jobs (system.lakeflow.jobs, kind ``sql``).
      2. Count of un-scheduled jobs with recent runs — candidate external-scheduler
         targets (system.lakeflow.jobs + job_run_timeline, kind ``sql``).
      3. Caveat note on observability limits (kind ``note``).
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        # --- evidence 1: trigger type breakdown ---
        trigger_rows = ctx.sql.query(_SQL_TRIGGERS)
        trigger_row = trigger_rows[0] if trigger_rows else {}
        total_jobs = int(trigger_row.get("total_jobs") or 0)
        cron_scheduled = int(trigger_row.get("cron_scheduled") or 0)
        file_arrival_triggered = int(trigger_row.get("file_arrival_triggered") or 0)
        periodic_triggered = int(trigger_row.get("periodic_triggered") or 0)
        unscheduled_jobs = int(trigger_row.get("unscheduled_jobs") or 0)
        ev_triggers = Evidence(
            kind="sql",
            summary=(
                f"{total_jobs} active jobs: {cron_scheduled} CRON-scheduled, "
                f"{file_arrival_triggered} file-arrival, {periodic_triggered} periodic, "
                f"{unscheduled_jobs} with no Databricks-side trigger"
            ),
            detail=_SQL_TRIGGERS,
            rows=[{
                "total_jobs": total_jobs,
                "cron_scheduled": cron_scheduled,
                "file_arrival_triggered": file_arrival_triggered,
                "periodic_triggered": periodic_triggered,
                "unscheduled_jobs": unscheduled_jobs,
            }],
            ref=_REF,
        )

        # --- evidence 2: un-scheduled jobs with recent run history ---
        cand_rows = ctx.sql.query(_SQL_EXTERNAL_CANDIDATES)
        cand_row = cand_rows[0] if cand_rows else {}
        candidates = int(cand_row.get("external_scheduler_candidates") or 0)
        ev_candidates = Evidence(
            kind="sql",
            summary=(
                f"{candidates} un-scheduled job(s) have run in the last 30 days — "
                "possible external-scheduler integration"
            ),
            detail=_SQL_EXTERNAL_CANDIDATES,
            rows=[{"external_scheduler_candidates": candidates}],
            ref=_REF,
        )

        ev_note = Evidence(
            kind="note",
            summary=_NOTE_SUMMARY,
            rows=[],
            ref=_REF,
        )

        return [ev_triggers, ev_candidates, ev_note]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
