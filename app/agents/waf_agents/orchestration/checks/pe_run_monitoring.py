"""Workflow run-duration monitoring check (LLM-judged).

Answers:
  ORC-PE-04  Monitor workflow run durations and trends

Tracking whether job runs are taking longer over time is an important
performance-efficiency practice.  True monitoring requires dashboards or
alerting wired to job-run metrics — these are not observable in system tables.

The closest observable proxy is the run-duration distribution in
``system.lakeflow.job_run_timeline`` over the last 30 days:

  - A wide spread between min and max duration may indicate regressions.
  - Consistent duration (small spread) suggests stable, predictable runs.
  - Zero runs means the jobs are not executing (or are very new).

Whether those durations are being actively monitored and acted upon requires
Manual confirmation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT COUNT(*) AS total_runs,
       COUNT(DISTINCT run_id) AS distinct_runs,
       AVG(CAST(period_end_time AS DOUBLE) - CAST(period_start_time AS DOUBLE))
           AS avg_run_seconds,
       MAX(CAST(period_end_time AS DOUBLE) - CAST(period_start_time AS DOUBLE))
           AS max_run_seconds,
       MIN(CAST(period_end_time AS DOUBLE) - CAST(period_start_time AS DOUBLE))
           AS min_run_seconds
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS
  AND period_end_time IS NOT NULL\
"""

_NOTE = (
    "Active monitoring of workflow run durations and trends (dashboards, alerts, "
    "anomaly detection) is not observable in system tables.  The run-duration "
    "statistics above are a measurement proxy only; whether deviations trigger "
    "automated alerts or manual review requires manual confirmation."
)

_REF = "https://docs.databricks.com/en/jobs/job-run-details.html"


@register(layer="orchestration", question_ids=["ORC-PE-04"])
class OrcRunMonitoringCheck(Check):
    """Assess run-duration monitoring via job_run_timeline duration statistics.

    Evidence is gathered from ``system.lakeflow.job_run_timeline`` (last 30
    days): total runs, distinct runs, average, max, and min duration.  A large
    spread between min and max suggests duration variability that ideally is
    being tracked.  A note records that active monitoring tooling is not visible
    in system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            total = int(rows[0].get("total_runs") or 0)
            distinct = int(rows[0].get("distinct_runs") or 0)
            avg_raw = rows[0].get("avg_run_seconds")
            max_raw = rows[0].get("max_run_seconds")
            min_raw = rows[0].get("min_run_seconds")
            avg_secs = round(float(avg_raw), 1) if avg_raw is not None else None
            max_secs = round(float(max_raw), 1) if max_raw is not None else None
            min_secs = round(float(min_raw), 1) if min_raw is not None else None
        else:
            total = 0
            distinct = 0
            avg_secs = None
            max_secs = None
            min_secs = None

        if total > 0:
            dur_parts = []
            if avg_secs is not None:
                dur_parts.append(f"avg {avg_secs}s")
            if min_secs is not None and max_secs is not None:
                dur_parts.append(f"range {min_secs}–{max_secs}s")
            dur_str = (", " + ", ".join(dur_parts)) if dur_parts else ""
            summary = (
                f"{total} job-run intervals ({distinct} distinct runs) recorded "
                f"in the last 30 days{dur_str}"
            )
        else:
            summary = (
                "No workflow runs found in system.lakeflow.job_run_timeline for the last 30 days"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[{
                "total_runs": total,
                "distinct_runs": distinct,
                "avg_run_seconds": avg_secs,
                "max_run_seconds": max_secs,
                "min_run_seconds": min_secs,
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
