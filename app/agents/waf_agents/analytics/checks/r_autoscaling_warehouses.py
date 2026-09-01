"""SQL warehouse autoscaling check (deterministic).

Answers:
  ANA-R-01  Use autoscaling SQL warehouses

Signal: share of SQL warehouses that have autoscaling enabled, from
``system.compute.warehouses``. Autoscaling is inferred when
``max_num_clusters > min_num_clusters`` (multi-cluster scaling). A warehouse
with min = max = 1 is fixed-size and cannot absorb concurrent load spikes.

Deterministic ratio vs a threshold -> High confidence (direct system-table
count, not a proxy).
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.70
_PARTIAL_THRESHOLD = 0.40

_SQL = (
    "SELECT COUNT(*) AS total, "
    "SUM(CASE WHEN max_num_clusters > min_num_clusters THEN 1 ELSE 0 END) AS autoscaling "
    "FROM system.compute.warehouses"
)


@register(layer="analytics", question_ids=["ANA-R-01"])
class WarehouseAutoscalingCheck(Check):
    """Assess SQL warehouse autoscaling adoption.

    Evidence is gathered from ``system.compute.warehouses``: total warehouse
    count and those with max_num_clusters > min_num_clusters (multi-cluster
    autoscaling enabled). Warehouses with min = max clusters are fixed-size and
    cannot absorb concurrent user spikes.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total": 0, "autoscaling": 0}
        total = int(row.get("total") or 0)
        autoscaling = int(row.get("autoscaling") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{autoscaling} of {total} SQL warehouses have autoscaling enabled "
                    "(max_num_clusters > min_num_clusters)"
                ),
                detail=_SQL,
                rows=[{"total": total, "autoscaling": autoscaling}],
                ref="https://docs.databricks.com/en/compute/sql-warehouse/create-sql-warehouse.html",
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total"]
        autoscaling = row["autoscaling"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No SQL warehouses found in system.compute.warehouses; "
                    "cannot evaluate autoscaling coverage."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = autoscaling / total
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
                f"{autoscaling} of {total} SQL warehouses ({ratio:.0%}) have autoscaling enabled "
                f"(max_num_clusters > min_num_clusters); threshold for 'met' is "
                f"{_MET_THRESHOLD:.0%}. "
                "Fixed-size warehouses (min = max clusters) cannot scale horizontally "
                "under concurrent query load."
            ),
            sources=evidence,
        )
