"""AI quality degradation detection check (LLM-judged).

Answers:
  AI-R-05  Detect and respond to AI quality degradation

Evidence comes from ``system.serving.endpoint_usage`` aggregated by day:
error rates trended over the last 30 days.  A rising error rate is a weak
proxy for degradation that warrants investigation.

True AI quality degradation (hallucination rate, output coherence, downstream
task accuracy) is not observable from latency or error-rate telemetry alone.
Active quality monitoring (LLM-as-judge pipelines, human feedback loops,
A/B evaluation) requires manual confirmation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  CAST(request_time AS DATE) AS metric_date,
  COUNT(*) AS requests,
  SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_count
FROM system.serving.endpoint_usage
WHERE request_time >= current_timestamp() - INTERVAL 30 DAYS
GROUP BY CAST(request_time AS DATE)
ORDER BY metric_date\
"""

_NOTE = (
    "True AI quality degradation — hallucination rate, answer coherence, "
    "task accuracy — is not measurable from endpoint latency or error-rate "
    "telemetry alone.  Rising error rates or latency trends are indirect "
    "indicators only.  Detecting output-quality degradation requires LLM-as-judge "
    "pipelines, human feedback collection, or automated evaluation harnesses; "
    "a reviewer must confirm whether such monitoring is in place."
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/monitor-diagnose-endpoint.html"


@register(layer="ai", question_ids=["AI-R-05"])
class QualityDegradationCheck(Check):
    """Assess quality-degradation detection via error-rate and latency trends.

    Evidence: system.serving.endpoint_usage (last 30 days) by date — requests,
    error count, avg latency per day.  Trends in these metrics are a weak proxy.
    A note records that output-quality monitoring is not observable from
    telemetry alone.  LLM judges both.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if not rows:
            summary = (
                "No serving endpoint requests found in system.serving.endpoint_usage "
                "for the last 30 days — cannot assess quality-degradation signals"
            )
            evidence_rows: list[dict] = []
        else:
            day_count = len(rows)
            total_requests = sum(int(r.get("requests") or 0) for r in rows)
            total_errors = sum(int(r.get("error_count") or 0) for r in rows)
            overall_error_pct = (
                round(100.0 * total_errors / total_requests, 1) if total_requests else 0
            )
            # Compare first-week vs last-week error rates as a crude trend signal
            if day_count >= 14:
                first_week = rows[:7]
                last_week = rows[-7:]
                fw_req = sum(int(r.get("requests") or 0) for r in first_week)
                fw_err = sum(int(r.get("error_count") or 0) for r in first_week)
                lw_req = sum(int(r.get("requests") or 0) for r in last_week)
                lw_err = sum(int(r.get("error_count") or 0) for r in last_week)
                fw_rate = round(100.0 * fw_err / fw_req, 1) if fw_req else 0
                lw_rate = round(100.0 * lw_err / lw_req, 1) if lw_req else 0
                trend = f"error rate first-7d={fw_rate}% vs last-7d={lw_rate}%"
            else:
                trend = "insufficient days for trend comparison"
            summary = (
                f"{day_count} days of data, {total_requests} total requests, "
                f"overall error rate={overall_error_pct}%; {trend}"
            )
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
