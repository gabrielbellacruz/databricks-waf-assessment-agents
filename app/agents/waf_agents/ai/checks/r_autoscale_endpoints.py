"""Autoscaling AI endpoints check (LLM-judged).

Answers:
  AI-R-03  Autoscale AI endpoints to demand

Evidence comes from ``system.ai_gateway.usage`` aggregated by day: per-day
request counts and average latency over the last 30 days.  High variance in
daily request counts indicates that autoscaling would reduce cost/risk; latency
degradation on high-volume days is a proxy for insufficient concurrency.

Autoscale min/max concurrency and scale-to-zero configuration are endpoint
settings not exposed in usage tables — the observable signal is load variation
and latency-under-load.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  CAST(event_time AS DATE) AS request_date,
  COUNT(*) AS daily_request_count,
  AVG(latency_ms) AS avg_latency_ms
FROM system.ai_gateway.usage
WHERE event_time >= current_timestamp() - INTERVAL 30 DAYS
GROUP BY CAST(event_time AS DATE)
ORDER BY request_date\
"""

_NOTE = (
    "Autoscale configuration (min/max concurrency, scale-to-zero) is an endpoint "
    "setting not visible in system.ai_gateway.usage.  Day-to-day variance in "
    "request volume and latency-under-load are indirect proxies: high variance "
    "suggests demand spikes where autoscaling reduces cost or prevents throttling, "
    "but whether autoscaling is actually enabled requires manual inspection of endpoint "
    "configuration."
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/configure-model-serving-resources.html"


@register(layer="ai", question_ids=["AI-R-03"])
class AutoscaleEndpointsCheck(Check):
    """Assess autoscaling posture via day-by-day request volume variation.

    Evidence: system.serving.endpoint_usage (last 30 days) grouped by date —
    per-day request counts and average latency.  Load variance is a proxy for
    the need for autoscaling; a note records that scale config is not observable.
    LLM judges both pieces.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        day_count = len(rows)
        if day_count == 0:
            summary = (
                "No serving endpoint requests found in system.serving.endpoint_usage "
                "for the last 30 days — cannot assess autoscaling demand"
            )
            evidence_rows: list[dict] = []
        else:
            counts = [int(r.get("daily_request_count") or 0) for r in rows]
            max_req = max(counts)
            min_req = min(counts)
            avg_req = round(sum(counts) / day_count, 1)
            variance_tag = (
                "high demand variance detected"
                if max_req > 3 * avg_req
                else "demand is relatively stable"
            )
            summary = (
                f"{day_count} days of data; daily requests min={min_req}, "
                f"avg={avg_req}, max={max_req} — {variance_tag}"
            )
            # Cap rows at 10 for the evidence block
            evidence_rows = rows[:10]

        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=evidence_rows,
                ref=_REF,
            ),
            Evidence(kind="note", summary=_NOTE, rows=[], ref=_REF),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
