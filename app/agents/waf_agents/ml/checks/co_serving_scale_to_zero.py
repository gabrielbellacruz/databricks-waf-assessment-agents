"""Serving endpoint scale-to-zero check (deterministic).

Answers:
  ML-CO-04  Scale serving endpoints to zero when idle

Signal: model-serving DBU cost from ``system.billing.usage`` correlated with
request activity from ``system.serving.endpoint_usage``, bucketed per endpoint
per hour over the last 30 days. An endpoint configured for scale-to-zero incurs
no DBU during idle hours (it produces no billing rows), so those hours never
count as idle cost; an endpoint without scale-to-zero keeps accruing DBU even
in hours with zero requests -- those are the idle-cost hours.

The compliance ratio is (all billed endpoint-hours) minus (billed endpoint-hours
with zero requests) divided by (all billed endpoint-hours). A high ratio
indicates that billed time is matched by traffic -- scale-to-zero is working.
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
    "WITH cost AS ("
    "  SELECT usage_metadata.endpoint_id AS endpoint_id, "
    "         date_trunc('HOUR', usage_start_time) AS hr, "
    "         SUM(usage_quantity) AS dbu "
    "  FROM system.billing.usage "
    "  WHERE billing_origin_product = 'MODEL_SERVING' "
    f"    AND usage_start_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS "
    "    AND usage_metadata.endpoint_id IS NOT NULL "
    "  GROUP BY 1, 2"
    "), activity AS ("
    "  SELECT se.endpoint_id AS endpoint_id, "
    "         date_trunc('HOUR', eu.request_time) AS hr, "
    "         COUNT(*) AS requests "
    "  FROM system.serving.endpoint_usage eu "
    "  JOIN system.serving.served_entities se USING (served_entity_id) "
    f"  WHERE eu.request_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS "
    "  GROUP BY 1, 2"
    ") "
    "SELECT COUNT(*) AS total_endpoint_hours, "
    "       SUM(CASE WHEN c.dbu > 0 AND COALESCE(a.requests, 0) = 0 "
    "                THEN 1 ELSE 0 END) AS idle_cost_hours "
    "FROM cost c "
    "LEFT JOIN activity a ON c.endpoint_id = a.endpoint_id AND c.hr = a.hr"
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
