"""Pipeline complexity check (LLM-judged).

Answers:
  PRO-IU-01  Reduce complexity of transformation pipelines

Signal: the ratio of DLT/Lakeflow declarative pipelines to total processing
workloads (pipelines + jobs) from system tables, and the recent run failure
rate from ``system.lakeflow.job_run_timeline``.

Declarative DLT/Lakeflow pipelines are inherently lower-complexity than
hand-coded job task graphs; a high pipeline-to-workload ratio suggests the
team has adopted a simpler paradigm.  A high job-run failure rate is an
indirect signal of over-complex or brittle pipelines.  Task-level nesting
depth and per-job task counts are not exposed in system tables, so a note
records this limit.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_PIPELINES = "SELECT COUNT(*) AS pipeline_count FROM system.lakeflow.pipelines"

_SQL_JOBS = "SELECT COUNT(*) AS job_count FROM system.lakeflow.jobs WHERE delete_time IS NULL"

_SQL_RUNS = """\
SELECT COUNT(*) AS total_runs,
       SUM(CASE WHEN result_state IN ('FAILED', 'ERROR') THEN 1 ELSE 0 END) AS failed_runs
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Per-job task count, pipeline graph depth, and notebook/file sizes are not "
    "exposed in system tables available to this agent; pipeline count vs job count "
    "and recent failure rate are the best observable proxies for pipeline complexity. "
    "Manual review of specific job task graphs is recommended."
)

_REF = "https://docs.databricks.com/en/delta-live-tables/index.html"


@register(layer="processing", question_ids=["PRO-IU-01"])
class ProcessingPipelineComplexityCheck(Check):
    """Assess transformation-pipeline complexity.

    Evidence:
      1. DLT/Lakeflow pipeline count vs total jobs (pipeline ratio signals
         adoption of a simpler declarative paradigm).
      2. Recent job-run failure rate (high failure rate is a complexity risk).
      3. Note recording that per-job task depth is not enumerable.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        pipeline_rows = ctx.sql.query(_SQL_PIPELINES)
        job_rows = ctx.sql.query(_SQL_JOBS)
        run_rows = ctx.sql.query(_SQL_RUNS)

        pipeline_count = int(
            (pipeline_rows[0].get("pipeline_count") or 0) if pipeline_rows else 0
        )
        job_count = int(
            (job_rows[0].get("job_count") or 0) if job_rows else 0
        )
        total_runs = int((run_rows[0].get("total_runs") or 0) if run_rows else 0)
        failed_runs = int((run_rows[0].get("failed_runs") or 0) if run_rows else 0)

        total_workloads = pipeline_count + job_count
        pipeline_ratio = (
            round(pipeline_count / total_workloads, 2) if total_workloads > 0 else None
        )
        failure_rate = round(failed_runs / total_runs, 3) if total_runs > 0 else None

        workload_evidence = Evidence(
            kind="sql",
            summary=(
                f"{pipeline_count} DLT/Lakeflow pipeline(s) and {job_count} job(s) "
                f"(pipeline ratio: {pipeline_ratio if pipeline_ratio is not None else 'n/a'})"
            ),
            detail=f"{_SQL_PIPELINES} ; {_SQL_JOBS}",
            rows=[
                {
                    "pipeline_count": pipeline_count,
                    "job_count": job_count,
                    "pipeline_ratio": pipeline_ratio,
                }
            ],
            ref=_REF,
        )
        run_evidence = Evidence(
            kind="sql",
            summary=(
                f"{total_runs} job run(s) in the last 30 days; "
                f"{failed_runs} failed "
                f"(failure rate: {f'{failure_rate:.1%}' if failure_rate is not None else 'n/a'})"
            ),
            detail=_SQL_RUNS,
            rows=[
                {
                    "total_runs": total_runs,
                    "failed_runs": failed_runs,
                    "failure_rate": failure_rate,
                }
            ],
            ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
        )
        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [workload_evidence, run_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
