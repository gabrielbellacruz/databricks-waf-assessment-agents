"""Warehouse concurrency and scaling check (deterministic).

Answers:
  ANA-OE-05  Manage warehouse concurrency and scaling

Signal: share of SQL warehouses that have multi-cluster scaling enabled
(max_clusters > 1), derived from system.compute.warehouses.
A warehouse with max_clusters <= 1 has no automatic horizontal scaling and
will queue queries at peak load rather than spinning up additional clusters.

Thresholds: met >= 0.80, partial >= 0.40.
Denominator 0 (no warehouses found) -> UNKNOWN/LOW.
Deterministic ratio -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_SQL = (
    "SELECT COUNT(*) AS total_warehouses, "
    "SUM(CASE WHEN max_clusters > 1 THEN 1 ELSE 0 END) AS scaling_warehouses, "
    "SUM(CASE WHEN auto_stop_minutes > 0 THEN 1 ELSE 0 END) AS autostop_warehouses "
    "FROM system.compute.warehouses "
    "WHERE delete_time IS NULL"
)

_MET_THRESHOLD = 0.80
_PARTIAL_THRESHOLD = 0.40

_REF = "https://docs.databricks.com/en/sql/admin/create-sql-warehouse.html"


@register(layer="analytics", question_ids=["ANA-OE-05"])
class WarehouseScalingCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        total = int((rows[0].get("total_warehouses") if rows else None) or 0)
        scaling = int((rows[0].get("scaling_warehouses") if rows else None) or 0)
        autostop = int((rows[0].get("autostop_warehouses") if rows else None) or 0)

        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{scaling} of {total} SQL warehouses have multi-cluster scaling enabled "
                    f"(max_clusters > 1); {autostop} have auto-stop configured"
                ),
                detail=_SQL,
                rows=[
                    {
                        "total_warehouses": total,
                        "scaling_warehouses": scaling,
                        "autostop_warehouses": autostop,
                    }
                ],
                ref=_REF,
            )
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        row = evidence[0].rows[0]
        total = row["total_warehouses"]
        scaling = row["scaling_warehouses"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No SQL warehouses found in system.compute.warehouses; "
                    "cannot assess scaling configuration."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = min(1.0, scaling / total)
        if ratio >= _MET_THRESHOLD:
            verdict = Verdict.MET
        elif ratio >= _PARTIAL_THRESHOLD:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.NOT_MET

        return Finding(
            question_id=question.id,
            pillar_id=question.pillar_id,
            verdict=verdict,
            confidence=Confidence.HIGH,
            score=round(ratio, 4),
            rationale=(
                f"{scaling} of {total} SQL warehouses ({ratio:.0%}) have multi-cluster "
                f"scaling enabled; threshold for 'met' is ≥{_MET_THRESHOLD:.0%}."
            ),
            sources=evidence,
        )
