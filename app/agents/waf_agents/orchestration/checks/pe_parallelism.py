"""Task parallelism check for orchestration (LLM-judged).

Answers:
  ORC-PE-01  Parallelize independent workflow tasks

Databricks Workflows executes tasks in parallel when no dependency edge links
them.  The presence of multi-task jobs (``array_size(tasks) > 1``) in
``system.lakeflow.jobs`` is a necessary condition for parallelism but not
sufficient — tasks could be purely sequential (each depending on the previous).

The average run duration from ``system.lakeflow.job_run_timeline`` provides
an indirect complementary signal: a very short elapsed time for multi-task
jobs hints that tasks ran concurrently rather than serially.

Actual dependency graph topology is embedded in the tasks array and is not
easily aggregated in a single count — the LLM judge weighs both evidence
pieces and the configuration gap.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_TASKS = """\
SELECT COUNT(*) AS total_jobs,
       SUM(CASE WHEN array_size(tasks) > 1 THEN 1 ELSE 0 END) AS multi_task_jobs
FROM system.lakeflow.jobs
WHERE delete_time IS NULL\
"""

_SQL_DURATION = """\
SELECT COUNT(DISTINCT run_id) AS total_runs,
       AVG(CAST(period_end_time AS DOUBLE) - CAST(period_start_time AS DOUBLE))
           AS avg_run_seconds
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Multi-task job count indicates jobs *capable* of task-level parallelism, "
    "but actual parallelism depends on whether tasks have dependency edges.  "
    "The task dependency graph is embedded in the tasks array struct and is not "
    "aggregatable from system.lakeflow.jobs without per-job inspection.  Manual "
    "review of job dependency configurations is required to confirm parallelism."
)

_REF = "https://docs.databricks.com/en/jobs/create-run-jobs.html#add-task-dependencies"


@register(layer="orchestration", question_ids=["ORC-PE-01"])
class OrcParallelismCheck(Check):
    """Assess task parallelism via multi-task job count and run duration signals.

    Evidence is gathered from:
      - ``system.lakeflow.jobs``             (multi-task job count)
      - ``system.lakeflow.job_run_timeline`` (avg run duration as parallelism proxy)
    A note records that actual dependency topology is not observable in summary
    system-table queries.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        # --- evidence 1: multi-task job count ---
        task_rows = ctx.sql.query(_SQL_TASKS)
        task_row = task_rows[0] if task_rows else {}
        total_jobs = int(task_row.get("total_jobs") or 0)
        multi_task = int(task_row.get("multi_task_jobs") or 0)

        ev_tasks = Evidence(
            kind="sql",
            summary=(
                f"{multi_task} of {total_jobs} active jobs have more than one task "
                "(candidate for task-level parallelism)"
            ),
            detail=_SQL_TASKS,
            rows=[{"total_jobs": total_jobs, "multi_task_jobs": multi_task}],
            ref=_REF,
        )

        # --- evidence 2: recent run durations ---
        dur_rows = ctx.sql.query(_SQL_DURATION)
        dur_row = dur_rows[0] if dur_rows else {}
        total_runs = int(dur_row.get("total_runs") or 0)
        avg_raw = dur_row.get("avg_run_seconds")
        avg_secs = round(float(avg_raw), 1) if avg_raw is not None else None

        if total_runs > 0:
            dur_str = f", avg duration {avg_secs}s" if avg_secs is not None else ""
            dur_summary = (
                f"{total_runs} workflow runs recorded in the last 30 days{dur_str}"
            )
        else:
            dur_summary = "No workflow runs found in job_run_timeline for the last 30 days"

        ev_duration = Evidence(
            kind="sql",
            summary=dur_summary,
            detail=_SQL_DURATION,
            rows=[{"total_runs": total_runs, "avg_run_seconds": avg_secs}],
            ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [ev_tasks, ev_duration, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
