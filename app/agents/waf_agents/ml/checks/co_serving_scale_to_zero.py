"""Serving endpoint scale-to-zero check (deterministic).

Answers:
  ML-CO-04  Scale serving endpoints to zero when idle

Signal: ``system.serving.endpoint_usage`` over the last 30 days. Each row
represents one hour of endpoint activity. An endpoint configured for
scale-to-zero will produce rows with ``serving_dbu_usage = 0`` during idle
hours (or no rows at all); an endpoint without scale-to-zero continues to
accrue ``serving_dbu_usage > 0`` even when ``total_tokens = 0``.

The compliance ratio is (all endpoint-hours) minus (idle endpoint-hours that
still incur cost) divided by (all endpoint-hours). A high ratio indicates
that idle time is not generating cost -- scale-to-zero is working.
Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.80
_PARTIAL_THRESHOLD = 0.40
_WINDOW_DAYS = 30

_SQL = (
    "SELECT "
    "COUNT(*) AS total_endpoint_hours, "
    "SUM(CASE WHEN serving_dbu_usage > 0 "
    "AND (total_tokens IS NULL OR total_tokens = 0) "
    "THEN 1 ELSE 0 END) AS idle_cost_hours "
    "FROM system.serving.endpoint_usage "
    f"WHERE hour >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS"
)

_REF = (
    "https://docs.databricks.com/en/machine-learning/model-serving/"
    "configure-serving-endpoints.html#scale-to-zero"
)


@register(layer="ml", question_ids=["ML-CO-04"])
class ServingScaleToZeroCheck(Check):
    """Deterministic check for ML-CO-04: serving endpoints scale to zero.

    Counts endpoint-hours where the endpoint incurred DBU cost despite zero
    token traffic (idle cost hours). Compliance ratio = 1 - (idle_cost_hours
    / total_endpoint_hours). A high compliance ratio means most idle time
    produces no cost, indicating scale-to-zero is configured and working.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total_endpoint_hours": 0, "idle_cost_hours": 0}
        total = int(row.get("total_endpoint_hours") or 0)
        idle_cost = int(row.get("idle_cost_hours") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{idle_cost} of {total} serving endpoint-hours (last {_WINDOW_DAYS}d) "
                    "incurred DBU cost with zero token traffic (idle cost hours)"
                ),
                detail=_SQL,
                rows=[{"total_endpoint_hours": total, "idle_cost_hours": idle_cost}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total_endpoint_hours"]
        idle_cost = row["idle_cost_hours"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No serving endpoint usage records in the window; "
                    "cannot evaluate scale-to-zero configuration."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        compliance_ratio = (total - idle_cost) / total
        if compliance_ratio >= _MET_THRESHOLD:
            verdict = Verdict.MET
        elif compliance_ratio >= _PARTIAL_THRESHOLD:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.NOT_MET

        idle_share = idle_cost / total

        return Finding(
            question_id=question.id,
            pillar_id=question.pillar_id,
            verdict=verdict,
            confidence=Confidence.HIGH,
            score=round(compliance_ratio, 4),
            rationale=(
                f"{idle_cost} of {total} endpoint-hours ({idle_share:.0%}) incurred DBU "
                f"cost with zero token traffic over the last {_WINDOW_DAYS} days; "
                f"compliance ratio (non-idle-cost hours) is {compliance_ratio:.0%}. "
                f"Threshold for 'met' is {_MET_THRESHOLD:.0%}. Endpoints without "
                "scale-to-zero continue to accrue cost between requests."
            ),
            sources=evidence,
        )
