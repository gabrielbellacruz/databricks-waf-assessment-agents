"""Throughput-monitoring check (LLM-judged).

Answers:
  ING-PE-05  Monitor ingestion throughput and latency

True throughput (records/sec) and end-to-end latency vs SLA are pipeline/
streaming metrics that are not exposed in system tables. The closest observable
proxy is whether ingestion jobs run regularly and how long each run takes, both
readable from ``system.lakeflow.job_run_timeline``. The LLM judge weighs that
run-frequency/duration signal together with a note explaining the evidence gap
and returns a verdict a reviewer can confirm or override.
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
           AS avg_run_seconds
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_THROUGHPUT_NOTE = (
    "True ingestion throughput (records/sec) and end-to-end latency vs SLA are emitted by "
    "pipeline/streaming metrics and dashboards, not the system tables this agent reads. "
    "Run frequency/duration is only an indirect proxy that jobs are observed; whether "
    "throughput/latency is actively monitored requires manual confirmation."
)

_THROUGHPUT_REF = "https://docs.databricks.com/en/optimizations/index.html"


@register(layer="ingestion", question_ids=["ING-PE-05"])
class ThroughputMonitoringCheck(Check):
    """Assess throughput/latency monitoring via recent job-run frequency and duration.

    Evidence is gathered from ``system.lakeflow.job_run_timeline`` (last 30
    days). A dominant note evidence records that true throughput/latency is not
    visible to the agent and must be confirmed manually. The LLM judge weighs
    both pieces and produces a verdict.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            total = int(rows[0].get("total_runs") or 0)
            distinct = int(rows[0].get("distinct_runs") or 0)
            avg_secs_raw = rows[0].get("avg_run_seconds")
            avg_secs = round(float(avg_secs_raw), 1) if avg_secs_raw is not None else None
        else:
            total = 0
            distinct = 0
            avg_secs = None

        if total > 0:
            dur_str = f", avg duration {avg_secs}s" if avg_secs is not None else ""
            summary = (
                f"{total} job-run intervals ({distinct} distinct runs) recorded "
                f"in system.lakeflow.job_run_timeline over the last 30 days{dur_str}"
            )
        else:
            summary = (
                "No job runs found in system.lakeflow.job_run_timeline for the last 30 days"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[{"total_runs": total, "distinct_runs": distinct, "avg_run_seconds": avg_secs}],
            ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_THROUGHPUT_NOTE,
            rows=[],
            ref=_THROUGHPUT_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
