"""Bottleneck identification check (LLM-judged).

Answers:
  PRO-PE-04  Identify bottlenecks in transformation chains

Identifying bottlenecks in transformation chains typically requires Spark UI /
Query Profile analysis, which is not available in system tables.  The closest
observable proxy is job-run duration and failure statistics from
``system.lakeflow.job_run_timeline``: jobs with very high average durations or
with a high failure/timeout rate are a signal that the team may be encountering
(but not resolving) bottlenecks.  The LLM judge weighs the evidence and returns
a verdict a reviewer can confirm or override.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  COUNT(*) AS total_runs,
  SUM(CASE WHEN result_state IN ('FAILED','ERROR','TIMED_OUT') THEN 1 ELSE 0 END)
      AS failed_runs,
  AVG(CAST(period_end_time AS DOUBLE) - CAST(period_start_time AS DOUBLE))
      AS avg_run_seconds,
  MAX(CAST(period_end_time AS DOUBLE) - CAST(period_start_time AS DOUBLE))
      AS max_run_seconds
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_BOTTLENECK_NOTE = (
    "Spark UI and Query Profile are the primary tools for identifying bottlenecks "
    "(skew, shuffle spill, slow stages, inefficient plans).  These data are not "
    "available in system tables.  Job duration and failure counts are only indirect "
    "signals that bottlenecks may exist.  Manual investigation via the Spark UI or "
    "Databricks Query Profile is required to pinpoint and resolve bottlenecks."
)

_BOTTLENECK_REF = "https://docs.databricks.com/en/optimizations/spark-ui-guide/index.html"


@register(layer="processing", question_ids=["PRO-PE-04"])
class BottleneckIdentificationCheck(Check):
    """Assess bottleneck identification readiness via job-run duration and failure stats.

    Evidence is gathered from ``system.lakeflow.job_run_timeline`` (last 30
    days).  Total runs, failure rate, average duration, and maximum duration are
    reported.  A note evidence records that Spark UI / Query Profile analysis is
    needed for true bottleneck identification and is not available here.  The LLM
    judge weighs both pieces and produces a verdict.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            total_runs = int(row.get("total_runs") or 0)
            failed_runs = int(row.get("failed_runs") or 0)
            avg_secs_raw = row.get("avg_run_seconds")
            max_secs_raw = row.get("max_run_seconds")
            avg_secs = round(float(avg_secs_raw), 1) if avg_secs_raw is not None else None
            max_secs = round(float(max_secs_raw), 1) if max_secs_raw is not None else None
        else:
            total_runs = 0
            failed_runs = 0
            avg_secs = None
            max_secs = None

        if total_runs > 0:
            failure_pct = round(100.0 * failed_runs / total_runs, 1)
            dur_str = ""
            if avg_secs is not None:
                dur_str = f", avg={avg_secs}s, max={max_secs}s"
            summary = (
                f"{total_runs} job runs in the last 30 days: "
                f"{failed_runs} failed/errored/timed-out ({failure_pct}%){dur_str}"
            )
        else:
            summary = "No job runs found in system.lakeflow.job_run_timeline for the last 30 days"
            failure_pct = 0.0

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[
                {
                    "total_runs": total_runs,
                    "failed_runs": failed_runs,
                    "avg_run_seconds": avg_secs,
                    "max_run_seconds": max_secs,
                }
            ],
            ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_BOTTLENECK_NOTE,
            rows=[],
            ref=_BOTTLENECK_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
