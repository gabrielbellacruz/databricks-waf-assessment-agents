"""Pipeline and job performance monitoring check (LLM-judged).

Answers:
  PRO-PE-05  Monitor pipeline and job performance

There is no system-table column that directly records whether email or webhook
alerts are configured on a processing job.  The closest observable proxy is
the *observed failure rate* and run-frequency pattern from
``system.lakeflow.job_run_timeline``: a workspace where performance monitoring
is absent or broken will tend to accumulate unnoticed failures and show erratic
run durations.  The LLM judge weighs that signal together with a note explaining
the gap, and returns a verdict a reviewer can confirm or override.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT COUNT(*) AS total_runs,
       COUNT(DISTINCT run_id) AS distinct_runs,
       SUM(CASE WHEN result_state IN ('FAILED','ERROR','TIMED_OUT') THEN 1 ELSE 0 END)
           AS failed_runs,
       AVG(CAST(period_end_time AS DOUBLE) - CAST(period_start_time AS DOUBLE))
           AS avg_run_seconds
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_MONITORING_NOTE = (
    "Alert/notification *configuration* (email/webhook on failure or SLA breach) is not "
    "exposed in system tables and the agent's service principal cannot enumerate other "
    "teams' job notification settings, so this check assesses observed failure volume "
    "and run frequency as a proxy for monitoring health; whether alerts are wired "
    "requires manual confirmation."
)

_MONITORING_REF = "https://docs.databricks.com/en/jobs/job-notifications.html"


@register(layer="processing", question_ids=["PRO-PE-05"])
class PerformanceMonitoringCheck(Check):
    """Assess processing-job performance monitoring via run frequency and failure rate.

    Evidence is gathered from ``system.lakeflow.job_run_timeline`` (last 30
    days).  Total runs, distinct runs, failure rate, and average run duration
    are reported.  A note evidence records that alert *configuration* is not
    visible to the agent and must be confirmed manually.  The LLM judge weighs
    both pieces and produces a verdict capped at medium confidence.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            total_runs = int(row.get("total_runs") or 0)
            distinct_runs = int(row.get("distinct_runs") or 0)
            failed_runs = int(row.get("failed_runs") or 0)
            avg_secs_raw = row.get("avg_run_seconds")
            avg_secs = round(float(avg_secs_raw), 1) if avg_secs_raw is not None else None
        else:
            total_runs = 0
            distinct_runs = 0
            failed_runs = 0
            avg_secs = None

        if total_runs > 0:
            failure_pct = round(100.0 * failed_runs / total_runs, 1)
            dur_str = f", avg duration {avg_secs}s" if avg_secs is not None else ""
            summary = (
                f"{total_runs} job-run intervals ({distinct_runs} distinct runs) in the last "
                f"30 days; {failed_runs} failed/errored/timed-out ({failure_pct}%){dur_str}"
            )
        else:
            failure_pct = 0.0
            summary = "No job runs found in system.lakeflow.job_run_timeline for the last 30 days"

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[
                {
                    "total_runs": total_runs,
                    "distinct_runs": distinct_runs,
                    "failed_runs": failed_runs,
                    "avg_run_seconds": avg_secs,
                    "failure_pct": failure_pct,
                }
            ],
            ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_MONITORING_NOTE,
            rows=[],
            ref=_MONITORING_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
