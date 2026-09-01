"""Automation framework adoption check for orchestration (LLM-judged).

Answers:
  ORC-R-03  Use a job automation framework with built-in recovery

Databricks Workflows is the recommended job automation framework.  Its
presence is directly observable: any non-deleted entry in
``system.lakeflow.jobs`` means the workspace has at least one workflow job.
Built-in recovery features — email/webhook notifications, repair runs, and
``run_if`` task conditions — are configuration-level settings not exposed
in system tables.

The run success/failure breakdown from ``system.lakeflow.job_run_timeline``
provides an indirect signal for how well recovery is working in practice.
The LLM judge weighs both the adoption evidence and the configuration gap.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_JOBS = """\
SELECT COUNT(*) AS active_jobs
FROM system.lakeflow.jobs
WHERE delete_time IS NULL\
"""

_SQL_RUNS = """\
SELECT COUNT(*) AS total_runs,
       SUM(CASE WHEN result_state = 'SUCCEEDED' THEN 1 ELSE 0 END) AS succeeded_runs,
       SUM(CASE WHEN result_state IN ('FAILED','ERROR') THEN 1 ELSE 0 END) AS failed_runs
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Databricks Workflows (Lakeflow) is the recommended automation framework.  "
    "Built-in recovery features such as job notifications, repair runs, and "
    "task-level run conditions are Jobs-API configuration settings and are not "
    "visible in system tables.  The active-job count and run outcome breakdown "
    "are adoption and health proxies only — manual review of job configurations is "
    "required to confirm recovery capabilities are enabled."
)

_REF = "https://docs.databricks.com/en/jobs/index.html"


@register(layer="orchestration", question_ids=["ORC-R-03"])
class OrcAutomationFrameworkCheck(Check):
    """Assess automation-framework adoption via active workflow jobs and run outcomes.

    Evidence is gathered from:
      - ``system.lakeflow.jobs``         (active job count)
      - ``system.lakeflow.job_run_timeline`` (run success/failure rate, 30 days)
    A note records that recovery-feature configuration (alerts, repair runs,
    run_if conditions) is not visible in system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        # --- evidence 1: active workflow jobs ---
        job_rows = ctx.sql.query(_SQL_JOBS)
        active_jobs = int((job_rows[0].get("active_jobs") or 0) if job_rows else 0)

        ev_jobs = Evidence(
            kind="sql",
            summary=(
                f"{active_jobs} active workflow jobs in system.lakeflow.jobs — "
                "Databricks Workflows is" + (" in use" if active_jobs > 0 else " not detected")
            ),
            detail=_SQL_JOBS,
            rows=[{"active_jobs": active_jobs}],
            ref=_REF,
        )

        # --- evidence 2: recent run outcomes ---
        run_rows = ctx.sql.query(_SQL_RUNS)
        if run_rows:
            total = int(run_rows[0].get("total_runs") or 0)
            succeeded = int(run_rows[0].get("succeeded_runs") or 0)
            failed = int(run_rows[0].get("failed_runs") or 0)
        else:
            total = 0
            succeeded = 0
            failed = 0

        if total > 0:
            run_summary = (
                f"{total} workflow runs in the last 30 days: "
                f"{succeeded} SUCCEEDED, {failed} FAILED/ERROR"
            )
        else:
            run_summary = "No workflow job runs found in job_run_timeline for the last 30 days"

        ev_runs = Evidence(
            kind="sql",
            summary=run_summary,
            detail=_SQL_RUNS,
            rows=[{"total_runs": total, "succeeded_runs": succeeded, "failed_runs": failed}],
            ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [ev_jobs, ev_runs, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
