"""Event-driven file ingestion check (LLM-judged).

Answers:
  ING-OE-01  Use automated, event-driven file ingestion

Two workspace-wide SQL signals are gathered via ctx.sql:
  1. Jobs with a file-arrival trigger (system.lakeflow.jobs).
     ``trigger.file_arrival IS NOT NULL`` identifies jobs that start when new
     files land in cloud storage rather than on a fixed schedule or manually.
  2. Auto Loader (cloud_files) usage in the last 30 days
     (system.query.history, ILIKE '%cloud_files%').
     Cloud Files is the Databricks Auto Loader source format; its presence in
     query history is a strong proxy for event-driven ingestion adoption.

The LLM judge weighs both signals; ctx.artifacts is not used by this check.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_REF = "https://docs.databricks.com/en/ingestion/auto-loader/index.html"

_SQL_FILE_ARRIVAL = """\
SELECT COUNT(*) AS total_jobs,
       SUM(CASE WHEN trigger.file_arrival IS NOT NULL THEN 1 ELSE 0 END)
           AS file_arrival_jobs
FROM system.lakeflow.jobs
WHERE delete_time IS NULL\
"""

_SQL_AUTOLOADER = """\
SELECT COUNT(*) AS autoloader_statements
FROM system.query.history
WHERE statement_text ILIKE '%cloud_files%'
  AND start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""


@register(layer="ingestion", question_ids=["ING-OE-01"])
class EventDrivenIngestionCheck(Check):
    """Check whether the workspace uses automated, event-driven file ingestion.

    Evidence is gathered purely from system tables (ctx.sql):
      - system.lakeflow.jobs  -> jobs with a file-arrival trigger
      - system.query.history  -> recent Auto Loader (cloud_files) statements
    The LLM judge renders a verdict from the two evidence items.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        # --- evidence 1: jobs with a file-arrival trigger ---
        job_rows = ctx.sql.query(_SQL_FILE_ARRIVAL)
        job_row = job_rows[0] if job_rows else {}
        total_jobs = int(job_row.get("total_jobs") or 0)
        file_arrival_jobs = int(job_row.get("file_arrival_jobs") or 0)
        ev_jobs = Evidence(
            kind="sql",
            summary=(
                f"{file_arrival_jobs} of {total_jobs} jobs use a file-arrival trigger"
            ),
            detail=_SQL_FILE_ARRIVAL,
            rows=[{"total_jobs": total_jobs, "file_arrival_jobs": file_arrival_jobs}],
            ref=_REF,
        )

        # --- evidence 2: Auto Loader usage in query history ---
        al_rows = ctx.sql.query(_SQL_AUTOLOADER)
        al_row = al_rows[0] if al_rows else {}
        autoloader_statements = int(al_row.get("autoloader_statements") or 0)
        ev_al = Evidence(
            kind="sql",
            summary=(
                f"{autoloader_statements} Auto Loader (cloud_files) statements "
                "executed in the past 30 days"
            ),
            detail=_SQL_AUTOLOADER,
            rows=[{"autoloader_statements": autoloader_statements}],
            ref=_REF,
        )

        return [ev_jobs, ev_al]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
