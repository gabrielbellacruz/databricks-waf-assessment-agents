"""Training and inference performance monitoring check (LLM-judged).

Answers:
  ML-PE-05  Monitor training and inference performance

Whether training duration and inference latency are *actively monitored*
(dashboards, alerting, regression detection) cannot be determined from
system tables. The observable proxies are:
  1. ``system.lakeflow.job_run_timeline`` — job durations confirm that
     training duration telemetry exists and is observable.
  2. ``system.serving.endpoint_usage`` — latency and throughput data
     confirm that inference performance is observable.
Presence of telemetry does not equal active monitoring; the LLM judge is
expected to note this distinction and score accordingly.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

# Distinct needle: "avg_duration_s" (unique to this check among ML checks)
_JOB_SQL = """\
SELECT
  COUNT(*) AS total_runs,
  ROUND(AVG(TIMESTAMPDIFF(SECOND, period_start_time, period_end_time)), 1) AS avg_duration_s,
  ROUND(MAX(TIMESTAMPDIFF(SECOND, period_start_time, period_end_time)), 1) AS max_duration_s
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS
  AND period_end_time IS NOT NULL\
"""

# Distinct needle: "total_requests" (unique to this check)
_SERVING_SQL = """\
SELECT
  COUNT(*) AS total_requests,
  ROUND(AVG(response_latency_ms), 1) AS avg_latency_ms,
  ROUND(MAX(response_latency_ms), 1) AS max_latency_ms,
  COUNT(DISTINCT endpoint_name) AS active_endpoints
FROM system.serving.endpoint_usage
WHERE timestamp >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "The presence of job-duration and serving-latency telemetry confirms that "
    "training and inference performance data is available and observable. However, "
    "this alone does not confirm that active monitoring dashboards, alerting policies, "
    "or performance regression detection are in place; manual confirmation is needed to "
    "assess whether performance is actively tracked against defined thresholds."
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/monitor-diagnose-endpoints.html"


@register(layer="ml", question_ids=["ML-PE-05"])
class MlPerformanceMonitoringCheck(Check):
    """Assess training and inference performance monitoring via available telemetry.

    Evidence is gathered from system.lakeflow.job_run_timeline (training
    run durations, last 30 days) and system.serving.endpoint_usage (inference
    latency, last 30 days). A note evidence records that telemetry presence
    does not equal active monitoring.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        evidence: list[Evidence] = []

        # 1. Training duration telemetry
        job_rows = ctx.sql.query(_JOB_SQL)
        if job_rows:
            row = job_rows[0]
            total_runs = int(row.get("total_runs") or 0)
            avg_dur = row.get("avg_duration_s")
            max_dur = row.get("max_duration_s")
        else:
            total_runs = 0
            avg_dur = max_dur = None

        if total_runs > 0:
            dur_str = (
                f"; avg={avg_dur}s, max={max_dur}s" if avg_dur is not None else ""
            )
            job_summary = (
                f"{total_runs} completed job runs in the last 30 days{dur_str} — "
                "training duration telemetry is observable"
            )
        else:
            job_summary = (
                "No completed job runs found in system.lakeflow.job_run_timeline "
                "for the last 30 days"
            )

        evidence.append(
            Evidence(
                kind="sql",
                summary=job_summary,
                detail=_JOB_SQL,
                rows=[
                    {
                        "total_runs": total_runs,
                        "avg_duration_s": avg_dur,
                        "max_duration_s": max_dur,
                    }
                ],
                ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
            )
        )

        # 2. Inference latency telemetry
        serving_rows = ctx.sql.query(_SERVING_SQL)
        if serving_rows:
            row = serving_rows[0]
            total_requests = int(row.get("total_requests") or 0)
            avg_lat = row.get("avg_latency_ms")
            max_lat = row.get("max_latency_ms")
            active_endpoints = int(row.get("active_endpoints") or 0)
        else:
            total_requests = active_endpoints = 0
            avg_lat = max_lat = None

        if total_requests > 0:
            lat_str = (
                f"; avg={avg_lat}ms, max={max_lat}ms" if avg_lat is not None else ""
            )
            serving_summary = (
                f"{total_requests:,} inference requests across {active_endpoints} "
                f"endpoint(s) in the last 30 days{lat_str} — "
                "inference latency telemetry is observable"
            )
        else:
            serving_summary = (
                "No serving endpoint traffic found in system.serving.endpoint_usage "
                "for the last 30 days"
            )

        evidence.append(
            Evidence(
                kind="sql",
                summary=serving_summary,
                detail=_SERVING_SQL,
                rows=[
                    {
                        "total_requests": total_requests,
                        "avg_latency_ms": avg_lat,
                        "max_latency_ms": max_lat,
                        "active_endpoints": active_endpoints,
                    }
                ],
                ref="https://docs.databricks.com/en/admin/system-tables/serving.html",
            )
        )

        evidence.append(
            Evidence(
                kind="note",
                summary=_NOTE,
                rows=[],
                ref=_REF,
            )
        )

        return evidence

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
