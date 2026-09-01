"""AI endpoint monitoring check (LLM-judged).

Answers:
  AI-OE-03  Monitor AI endpoints for quality, latency, and drift

Signals:
1. ``system.serving.endpoint_usage``: error rate (non-2xx / total requests) and
   total request volume over the last 30 days — a measurable proxy for whether
   endpoints are actively used and their error health observable.
2. ``system.ai_gateway.usage``: status-code distribution (2xx vs 4xx/5xx) to
   corroborate error rates and surface guardrail-blocked counts.

Limitations noted:
- Alert configuration (threshold alerts, Lakehouse Monitoring integration,
  custom dashboards) is NOT observable from system tables.
- Latency percentiles (p50/p99) are not surfaced in system.serving.endpoint_usage
  aggregates; only total execution time / request count is available.
- Model drift (output distribution shift over time) cannot be assessed from
  system tables alone.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_ENDPOINT_HEALTH_SQL = """\
SELECT endpoint_name,
       SUM(request_count) AS total_requests,
       SUM(CASE WHEN status_code >= 400 THEN request_count ELSE 0 END) AS error_requests,
       SUM(total_execution_time_ms) AS total_exec_ms
FROM system.serving.endpoint_usage
WHERE window_start_time >= current_timestamp() - INTERVAL 30 DAYS
GROUP BY endpoint_name
ORDER BY total_requests DESC
LIMIT 20\
"""

_GATEWAY_STATUS_SQL = """\
SELECT
  COUNT(*) AS total_calls,
  SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_calls,
  SUM(CASE WHEN guardrail_request_blocked = true
            OR guardrail_response_blocked = true THEN 1 ELSE 0 END) AS guardrail_blocked
FROM system.ai_gateway.usage
WHERE timestamp >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Error rate and request volume are observable signals for endpoint health, but "
    "'monitoring' requires alert configuration (latency thresholds, error-rate alerts, "
    "Lakehouse Monitoring for output drift) which is NOT visible in system tables. "
    "Latency percentiles (p99) are not available in system.serving.endpoint_usage aggregates. "
    "Model quality drift (output distribution shift) requires an external evaluation harness "
    "and is not captured in system tables. A reviewer must confirm alerting and drift "
    "detection are wired."
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/monitor-diagnose-endpoints.html"


@register(layer="ai", question_ids=["AI-OE-03"])
class EndpointMonitoringCheck(Check):
    """Assess AI endpoint monitoring via error rates and gateway status distribution.

    Evidence:
    - system.serving.endpoint_usage: per-endpoint error rate and request volume.
    - system.ai_gateway.usage: aggregate status-code and guardrail-block counts.
    A note records that alert configuration, p99 latency, and drift detection
    are not observable from system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        endpoint_rows = ctx.sql.query(_ENDPOINT_HEALTH_SQL)
        gateway_rows = ctx.sql.query(_GATEWAY_STATUS_SQL)

        if endpoint_rows:
            total_req = sum(int(r.get("total_requests") or 0) for r in endpoint_rows)
            total_err = sum(int(r.get("error_requests") or 0) for r in endpoint_rows)
            err_pct = round(100.0 * total_err / total_req, 1) if total_req > 0 else 0.0
            endpoint_summary = (
                f"{len(endpoint_rows)} AI endpoint(s) active; {total_req} total requests, "
                f"{total_err} errors ({err_pct}% error rate) in the last 30 days "
                "(system.serving.endpoint_usage)"
            )
        else:
            total_req = 0
            total_err = 0
            err_pct = 0.0
            endpoint_summary = (
                "No rows in system.serving.endpoint_usage for the last 30 days — "
                "no active AI endpoints found"
            )

        endpoint_evidence = Evidence(
            kind="sql",
            summary=endpoint_summary,
            detail=_ENDPOINT_HEALTH_SQL,
            rows=endpoint_rows[:20],
            ref="https://docs.databricks.com/en/admin/system-tables/serving.html",
        )

        if gateway_rows:
            g = gateway_rows[0]
            total_calls = int(g.get("total_calls") or 0)
            error_calls = int(g.get("error_calls") or 0)
            guardrail_blocked = int(g.get("guardrail_blocked") or 0)
            gw_err_pct = round(100.0 * error_calls / total_calls, 1) if total_calls > 0 else 0.0
            gateway_summary = (
                f"AI Gateway: {total_calls} calls, {error_calls} errors ({gw_err_pct}%), "
                f"{guardrail_blocked} guardrail-blocked in the last 30 days"
            )
        else:
            total_calls = 0
            error_calls = 0
            guardrail_blocked = 0
            gateway_summary = "No rows in system.ai_gateway.usage for the last 30 days"

        gateway_evidence = Evidence(
            kind="sql",
            summary=gateway_summary,
            detail=_GATEWAY_STATUS_SQL,
            rows=[{
                "total_calls": total_calls,
                "error_calls": error_calls,
                "guardrail_blocked": guardrail_blocked,
            }],
            ref="https://docs.databricks.com/en/ai-gateway/index.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [endpoint_evidence, gateway_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
