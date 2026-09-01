"""Endpoint latency and throughput monitoring check (LLM-judged).

Answers:
  AI-PE-05  Monitor endpoint latency and throughput

Evidence comes from ``system.serving.endpoint_usage``: active endpoints,
total requests, avg and max latency, and a derived avg-requests-per-day over
the last 30 days.  The presence and volume of this telemetry confirms that
latency and throughput data are available for monitoring.

Whether the workspace actively monitors these metrics — via dashboards, SLO
alerts, or automated anomaly detection — requires manual confirmation beyond the
mere existence of the telemetry.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  COUNT(DISTINCT endpoint_name) AS monitored_endpoints,
  COUNT(*) AS total_monitored_requests,
  AVG(execution_duration_ms) AS avg_latency_ms,
  MAX(execution_duration_ms) AS max_latency_ms,
  MIN(CAST(request_time AS DATE)) AS earliest_date,
  MAX(CAST(request_time AS DATE)) AS latest_date
FROM system.serving.endpoint_usage
WHERE request_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "The presence of telemetry in system.serving.endpoint_usage confirms that "
    "latency and throughput data are *available* for monitoring.  This does not "
    "confirm that active monitoring is in place: dashboards, SLO threshold alerts, "
    "or automated anomaly detection require manual review.  Databricks provides system "
    "tables and AI observability features, but they must be wired to alerting "
    "policies to constitute active monitoring."
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/monitor-diagnose-endpoint.html"


@register(layer="ai", question_ids=["AI-PE-05"])
class LatencyThroughputMonitoringCheck(Check):
    """Assess latency/throughput monitoring via endpoint usage telemetry.

    Evidence: system.serving.endpoint_usage (last 30 days) — active endpoints,
    total requests, avg/max latency, observation window.  Telemetry presence
    confirms data is available; a note records that active monitoring (dashboards,
    alerts) requires manual confirmation.  LLM judges.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            monitored_endpoints = int(row.get("monitored_endpoints") or 0)
            total_requests = int(row.get("total_monitored_requests") or 0)
            avg_ms_raw = row.get("avg_latency_ms")
            avg_ms = round(float(avg_ms_raw), 1) if avg_ms_raw is not None else None
            max_ms_raw = row.get("max_latency_ms")
            max_ms = int(max_ms_raw) if max_ms_raw is not None else None
            earliest = str(row.get("earliest_date") or "")
            latest = str(row.get("latest_date") or "")
        else:
            monitored_endpoints = total_requests = 0
            avg_ms = max_ms = None
            earliest = latest = ""

        if total_requests == 0:
            summary = (
                "No serving endpoint telemetry found in system.serving.endpoint_usage "
                "for the last 30 days — latency/throughput monitoring data unavailable"
            )
        else:
            window_str = f" ({earliest} to {latest})" if earliest and latest else ""
            lat_str = ""
            if avg_ms is not None:
                lat_str = f", avg={avg_ms}ms"
            if max_ms is not None:
                lat_str += f", max={max_ms}ms"
            summary = (
                f"Telemetry available: {monitored_endpoints} endpoint(s), "
                f"{total_requests} requests{lat_str}{window_str}; "
                "monitoring data exists — active alerting needs manual confirmation"
            )

        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=[{
                    "monitored_endpoints": monitored_endpoints,
                    "total_monitored_requests": total_requests,
                    "avg_latency_ms": avg_ms,
                    "max_latency_ms": max_ms,
                }],
                ref=_REF,
            ),
            Evidence(kind="note", summary=_NOTE, rows=[], ref=_REF),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
