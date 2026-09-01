"""Partial failure handling check for orchestration (LLM-judged).

Answers:
  ORC-R-02  Handle partial failures without full reruns

Databricks Workflows supports task-level run conditions (``run_if``) and repair
runs so that a failed task does not force a full job rerun.  These settings live
in the Jobs API configuration and are not exposed in system tables.

Observable proxies from ``system.lakeflow.job_run_timeline``:
  - ``SKIPPED`` result states indicate conditional task execution is in use
    (i.e. downstream tasks were deliberately bypassed after an upstream failure),
    which is evidence of partial-failure awareness.
  - The ratio of ``SUCCEEDED`` to total runs is a general run-health proxy.
The LLM judge weighs both signals and the configuration gap note.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT COUNT(*) AS total_runs,
       SUM(CASE WHEN result_state = 'SUCCEEDED' THEN 1 ELSE 0 END) AS succeeded_runs,
       SUM(CASE WHEN result_state = 'FAILED' THEN 1 ELSE 0 END) AS failed_runs,
       SUM(CASE WHEN result_state = 'SKIPPED' THEN 1 ELSE 0 END) AS skipped_runs
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Task-level run conditions (run_if: ALL_SUCCESS, AT_LEAST_ONE_FAILED, etc.) "
    "and repair-run capability are Jobs-API configuration settings not exposed in "
    "system tables.  The presence of SKIPPED result states in job_run_timeline is "
    "only an indirect proxy for conditional task execution — manual review of job task "
    "settings is required to confirm partial-failure handling."
)

_REF = "https://docs.databricks.com/en/jobs/repair-job-failures.html"


@register(layer="orchestration", question_ids=["ORC-R-02"])
class OrcPartialFailuresCheck(Check):
    """Assess partial-failure handling via SKIPPED task states and run outcomes.

    Evidence is gathered from ``system.lakeflow.job_run_timeline`` (last 30
    days).  SKIPPED runs indicate conditional task execution (run_if conditions),
    suggesting partial-failure-aware pipeline design.  A note records that the
    actual ``run_if`` settings and repair-run configuration are in the Jobs API
    and not visible here.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            total = int(rows[0].get("total_runs") or 0)
            succeeded = int(rows[0].get("succeeded_runs") or 0)
            failed = int(rows[0].get("failed_runs") or 0)
            skipped = int(rows[0].get("skipped_runs") or 0)
        else:
            total = 0
            succeeded = 0
            failed = 0
            skipped = 0

        if total > 0:
            summary = (
                f"{total} workflow task runs in the last 30 days: "
                f"{succeeded} SUCCEEDED, {failed} FAILED, {skipped} SKIPPED — "
                f"SKIPPED states indicate conditional (run_if) task execution"
            )
        else:
            summary = (
                "No workflow job runs found in system.lakeflow.job_run_timeline "
                "for the last 30 days"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[{
                "total_runs": total,
                "succeeded_runs": succeeded,
                "failed_runs": failed,
                "skipped_runs": skipped,
            }],
            ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
