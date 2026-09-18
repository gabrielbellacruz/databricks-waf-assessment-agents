"""Scalable, production-grade model serving check (LLM-judged).

Answers:
  AI-R-01  Use scalable, production-grade model serving

Evidence comes from ``system.ai_gateway.usage``: active endpoint count,
total request volume, average and p95 latency, and server-error rate over the
last 30 days.  Whether endpoints are configured for production-grade concurrency
or provisioned throughput is not observable from usage telemetry alone — the
LLM judge weighs the available proxy signals and a reviewer confirms scale config.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  COUNT(DISTINCT endpoint_name) AS endpoint_count,
  COUNT(*) AS total_requests,
  AVG(latency_ms) AS avg_latency_ms,
  percentile_approx(latency_ms, 0.95) AS p95_latency_ms,
  SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS server_error_count
FROM system.ai_gateway.usage
WHERE event_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Whether serving endpoints are configured for production-grade scale "
    "(min/max concurrency, provisioned throughput, autoscaling policy) is not "
    "directly observable from system.ai_gateway.usage.  The usage signal "
    "shows endpoints are actively used but cannot confirm that scale settings, "
    "health checks, or SLOs are defined — manual confirmation is needed. "
    "Latency here covers AI Gateway-routed endpoints (foundation-model and "
    "external-model serving); custom-model endpoints not routed through the "
    "gateway are not reflected in this signal."
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/index.html"


@register(layer="ai", question_ids=["AI-R-01"])
class ScalableServingCheck(Check):
    """Assess production-grade model serving via endpoint usage telemetry.

    Evidence: system.serving.endpoint_usage (last 30 days) — active endpoint
    count, request volume, avg/p95 latency, server-error rate.  A note records
    that scale configuration is not visible from usage tables.  LLM judges both.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        if rows:
            row = rows[0]
            endpoint_count = int(row.get("endpoint_count") or 0)
            total_requests = int(row.get("total_requests") or 0)
            avg_ms_raw = row.get("avg_latency_ms")
            avg_ms = round(float(avg_ms_raw), 1) if avg_ms_raw is not None else None
            p95_ms_raw = row.get("p95_latency_ms")
            p95_ms = round(float(p95_ms_raw), 1) if p95_ms_raw is not None else None
            server_errors = int(row.get("server_error_count") or 0)
        else:
            endpoint_count = total_requests = server_errors = 0
            avg_ms = p95_ms = None

        if total_requests == 0:
            summary = (
                "No serving endpoint requests found in system.serving.endpoint_usage "
                "for the last 30 days — cannot assess production usage"
            )
        else:
            error_pct = round(100.0 * server_errors / total_requests, 1)
            dur_str = ""
            if avg_ms is not None:
                dur_str = f", avg={avg_ms}ms"
            if p95_ms is not None:
                dur_str += f", p95={p95_ms}ms"
            summary = (
                f"{endpoint_count} active endpoint(s), {total_requests} requests"
                f"{dur_str} in last 30 days; "
                f"server errors: {server_errors} ({error_pct}%)"
            )

        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=[{
                    "endpoint_count": endpoint_count,
                    "total_requests": total_requests,
                    "avg_latency_ms": avg_ms,
                    "p95_latency_ms": p95_ms,
                    "server_error_count": server_errors,
                }],
                ref=_REF,
            ),
            Evidence(kind="note", summary=_NOTE, rows=[], ref=_REF),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
