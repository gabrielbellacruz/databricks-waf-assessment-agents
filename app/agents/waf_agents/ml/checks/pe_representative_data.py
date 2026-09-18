"""Model performance testing on representative data (LLM-judged).

Answers:
  ML-PE-04  Test model performance on representative data

Whether latency and throughput tests use production-representative data
(correct volume, distribution, data types) cannot be determined from system
tables alone. The observable proxy is serving-endpoint traffic in
``system.ai_gateway.usage``: a non-trivial request count with
latency distribution data shows that endpoints are receiving traffic and
performance is measurable. The LLM judge weighs this against the limitation
that system tables cannot confirm whether requests come from a benchmark/test
harness using representative data or from production traffic, or whether
any SLA thresholds have been defined.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

# Distinct needle: "p95_latency_ms"
_SQL = """\
SELECT
  endpoint_name,
  COUNT(*) AS request_count,
  ROUND(AVG(latency_ms), 1) AS avg_latency_ms,
  ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latency_ms), 1) AS p50_latency_ms,
  ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms), 1) AS p95_latency_ms,
  ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms), 1) AS p99_latency_ms
FROM system.ai_gateway.usage
WHERE event_time >= current_timestamp() - INTERVAL 30 DAYS
GROUP BY endpoint_name
ORDER BY request_count DESC
LIMIT 10\
"""

_NOTE = (
    "Whether performance tests use production-representative data (correct volume, "
    "data types, latency targets) cannot be inferred from system.ai_gateway.usage. "
    "Serving traffic confirms the endpoint is reachable and latency is observable, but "
    "does not distinguish benchmark traffic from production traffic, nor confirm that "
    "performance SLAs have been validated. Manual review of test harnesses and load-test "
    "results is required."
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/test-model-serving-endpoint.html"


@register(layer="ml", question_ids=["ML-PE-04"])
class MlRepresentativeDataCheck(Check):
    """Assess model performance testing via serving endpoint traffic and latency.

    Evidence is gathered from system.ai_gateway.usage (last 30 days):
    request counts and latency percentiles per endpoint. A note evidence
    records that representative-data testing versus production traffic is
    not distinguishable from system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            endpoint_count = len(rows)
            total_requests = sum(int(r.get("request_count") or 0) for r in rows)
            avg_p99 = round(
                sum(float(r.get("p99_latency_ms") or 0) for r in rows) / endpoint_count, 1
            ) if endpoint_count else None
            sql_summary = (
                f"{endpoint_count} endpoint(s) with traffic in the last 30 days; "
                f"{total_requests:,} total requests; avg p99 latency: {avg_p99} ms"
            )
        else:
            sql_summary = (
                "No serving endpoint traffic found in system.ai_gateway.usage "
                "for the last 30 days — cannot assess performance test coverage"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=sql_summary,
            detail=_SQL,
            rows=rows[:5],
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
