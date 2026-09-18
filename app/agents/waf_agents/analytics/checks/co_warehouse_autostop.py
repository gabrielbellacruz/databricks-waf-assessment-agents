"""Warehouse auto-stop check (deterministic).

Answers:
  ANA-CO-02  Enable warehouse auto-stop when idle

Signal: share of active (non-deleted) warehouses whose ``auto_stop_minutes`` is
greater than zero, from ``system.compute.warehouses``.  A non-zero value means
the warehouse shuts itself down after that many minutes of idle time.
Deterministic ratio vs threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.90
_PARTIAL_THRESHOLD = 0.50

_SQL = (
    "SELECT COUNT(*) AS total, "
    "SUM(CASE WHEN auto_stop_minutes > 0 THEN 1 ELSE 0 END) AS auto_stop "
    "FROM system.compute.warehouses "
    "WHERE delete_time IS NULL"
)


@register(layer="analytics", question_ids=["ANA-CO-02"])
class WarehouseAutoStopCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total": 0, "auto_stop": 0}
        total = int(row.get("total") or 0)
        auto_stop = int(row.get("auto_stop") or 0)
        return [
            Evidence(
                kind="sql",
                summary=f"{auto_stop} of {total} warehouses have auto-stop configured",
                detail=_SQL,
                rows=[{"total": total, "auto_stop": auto_stop}],
                ref=(
                    "https://docs.databricks.com/en/compute/sql-warehouse/"
                    "create-sql-warehouse.html#configure-auto-stop"
                ),
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total, auto_stop = row["total"], row["auto_stop"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale="No warehouses found to evaluate auto-stop coverage.",
                sources=evidence,
                auto_assessable=True,
            )

        ratio = auto_stop / total
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
                f"{auto_stop} of {total} warehouses ({ratio:.0%}) have auto-stop "
                f"configured (auto_stop_minutes > 0); threshold for 'met' is "
                f"{_MET_THRESHOLD:.0%}. Warehouses without auto-stop continue to "
                "accrue cost when idle."
            ),
            sources=evidence,
        )
