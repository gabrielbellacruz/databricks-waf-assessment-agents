"""API-driven orchestration check (LLM-judged).

Answers:
  ORC-IU-03  Orchestrate via open, API-driven interfaces

Whether teams drive workflow orchestration through open, API-driven interfaces
(REST API calls, webhooks, SDK-based job triggering) rather than purely through
the Databricks UI is not directly visible in system tables.

Three workspace-wide signals are gathered via ``ctx.sql``:
  1. The mix of trigger types across active jobs — CRON schedule, file-arrival,
     and continuous/periodic triggers — from ``system.lakeflow.jobs``.  A
     diverse set of non-UI trigger types indicates API or event-driven
     orchestration is in use.
  2. The count of distinct ``run_as`` identities on jobs started via an API
     (heuristic: service-principal identity without '@' suggests programmatic
     job management rather than interactive UI use).
  3. Total job count for scale context.

A note Evidence records the inherent limit of these proxy signals.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_TRIGGERS = (
    "SELECT COUNT(*) AS total_jobs, "
    "SUM(CASE WHEN trigger.schedule IS NOT NULL THEN 1 ELSE 0 END) AS cron_jobs, "
    "SUM(CASE WHEN trigger.file_arrival IS NOT NULL THEN 1 ELSE 0 END) AS file_arrival_jobs, "
    "SUM(CASE WHEN trigger.periodic IS NOT NULL THEN 1 ELSE 0 END) AS periodic_jobs "
    "FROM system.lakeflow.jobs "
    "WHERE delete_time IS NULL"
)

_SQL_API_OWNERS = (
    "SELECT COUNT(DISTINCT run_as) AS api_owners "
    "FROM system.lakeflow.jobs "
    "WHERE delete_time IS NULL "
    "AND run_as IS NOT NULL AND run_as NOT LIKE '%@%'"
)

_NOTE_SUMMARY = (
    "API-driven orchestration (REST API calls, SDK triggers, webhook invocations) "
    "is not directly distinguishable from UI-initiated actions in system tables. "
    "Trigger type diversity and service-principal identity are indirect proxies. "
    "Manual confirmation and API audit-log review needed."
)

_REF = "https://docs.databricks.com/en/workflows/jobs/jobs-2.0-api.html"


@register(layer="orchestration", question_ids=["ORC-IU-03"])
class ApiDrivenOrchestrationCheck(Check):
    """LLM-judged check for ORC-IU-03: API-driven orchestration interfaces.

    Evidence collected:
      1. Trigger-type breakdown for active jobs (system.lakeflow.jobs, kind ``sql``).
      2. Count of distinct service-principal run_as owners (kind ``sql``).
      3. Caveat note on observability limits (kind ``note``).
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        # --- evidence 1: trigger type breakdown ---
        trigger_rows = ctx.sql.query(_SQL_TRIGGERS)
        trigger_row = trigger_rows[0] if trigger_rows else {}
        total_jobs = int(trigger_row.get("total_jobs") or 0)
        cron_jobs = int(trigger_row.get("cron_jobs") or 0)
        file_arrival_jobs = int(trigger_row.get("file_arrival_jobs") or 0)
        periodic_jobs = int(trigger_row.get("periodic_jobs") or 0)
        ev_triggers = Evidence(
            kind="sql",
            summary=(
                f"{total_jobs} active jobs: {cron_jobs} CRON-scheduled, "
                f"{file_arrival_jobs} file-arrival triggered, "
                f"{periodic_jobs} periodic triggered"
            ),
            detail=_SQL_TRIGGERS,
            rows=[{
                "total_jobs": total_jobs,
                "cron_jobs": cron_jobs,
                "file_arrival_jobs": file_arrival_jobs,
                "periodic_jobs": periodic_jobs,
            }],
            ref=_REF,
        )

        # --- evidence 2: service-principal owners (proxy for API-managed jobs) ---
        api_rows = ctx.sql.query(_SQL_API_OWNERS)
        api_row = api_rows[0] if api_rows else {}
        api_owners = int(api_row.get("api_owners") or 0)
        ev_api = Evidence(
            kind="sql",
            summary=(
                f"{api_owners} distinct service-principal run_as identities "
                "on active jobs — a proxy for programmatic/API job management"
            ),
            detail=_SQL_API_OWNERS,
            rows=[{"api_owners": api_owners}],
            ref=_REF,
        )

        ev_note = Evidence(
            kind="note",
            summary=_NOTE_SUMMARY,
            rows=[],
            ref=_REF,
        )

        return [ev_triggers, ev_api, ev_note]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
