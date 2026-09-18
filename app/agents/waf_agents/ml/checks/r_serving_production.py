"""Production-grade model serving check (LLM-judged).

Answers:
  ML-R-01  Use scalable, production-grade model serving

Whether an endpoint is truly "production-grade" (autoscaling, health checks,
provisioned throughput, SLA) requires checking the serving endpoint config via
the API, which the agent's service principal cannot enumerate. The observable
proxy is traffic presence in ``system.ai_gateway.usage``: active endpoints
with non-trivial request counts and acceptable latencies are a positive signal;
absence of any endpoint traffic is a concern. The LLM judge weighs both pieces.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  endpoint_name,
  COUNT(*) AS request_count,
  ROUND(AVG(latency_ms), 1) AS avg_latency_ms,
  ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms), 1) AS p99_latency_ms
FROM system.ai_gateway.usage
WHERE event_time >= current_timestamp() - INTERVAL 30 DAYS
GROUP BY endpoint_name
ORDER BY request_count DESC
LIMIT 20\
"""

_NOTE = (
    "Whether serving endpoints are production-grade (autoscaling config, provisioned "
    "throughput, health checks, fallback behaviour) is an endpoint configuration setting "
    "not exposed in system.ai_gateway.usage. Active traffic with low latency is "
    "only a proxy — manual confirmation of endpoint configuration is needed. Latency "
    "telemetry covers endpoints routed through the AI Gateway (foundation-model and "
    "external-model serving)."
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/index.html"


@register(layer="ml", question_ids=["ML-R-01"])
class ServingProductionCheck(Check):
    """Assess production-grade model serving via endpoint-usage telemetry.

    Evidence is gathered from system.ai_gateway.usage over the last
    30 days: active endpoints, request counts and latency percentiles. A
    note evidence records that endpoint config (autoscaling, throughput) is
    not directly observable. The LLM judge weighs both pieces.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            endpoint_count = len(rows)
            total_requests = sum(int(r.get("request_count") or 0) for r in rows)
            avg_latency = round(
                sum(float(r.get("avg_latency_ms") or 0) for r in rows) / endpoint_count, 1
            ) if endpoint_count else None
            sql_summary = (
                f"{endpoint_count} serving endpoint(s) active in the last 30 days; "
                f"{total_requests:,} total requests; "
                f"avg latency across endpoints: {avg_latency} ms"
            )
        else:
            endpoint_count = 0
            total_requests = 0
            sql_summary = (
                "No serving endpoint traffic found in system.ai_gateway.usage "
                "for the last 30 days"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=sql_summary,
            detail=_SQL,
            rows=rows[:10],
            ref="https://docs.databricks.com/en/admin/system-tables/serving.html",
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
