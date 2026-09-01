"""Serverless SQL warehouse check (deterministic).

Answers:
  ANA-PE-01  Use serverless SQL warehouses for fast startup

Signal: share of SQL warehouses that are serverless, from
``system.compute.warehouses``. A warehouse is serverless when its
``warehouse_type`` is ``'SERVERLESS'`` or ``enable_serverless_compute`` is
``TRUE``. Serverless warehouses start in seconds (vs minutes for classic/pro)
and are billed per-query, eliminating idle capacity cost.

Deterministic ratio vs a threshold -> High confidence (direct warehouse
inventory, no proxy needed).
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.50
_PARTIAL_THRESHOLD = 0.20

_SQL = (
    "SELECT COUNT(*) AS total, "
    "SUM(CASE WHEN warehouse_type = 'SERVERLESS' OR enable_serverless_compute = TRUE "
    "THEN 1 ELSE 0 END) AS serverless_count "
    "FROM system.compute.warehouses"
)


@register(layer="analytics", question_ids=["ANA-PE-01"])
class ServerlessWarehousesCheck(Check):
    """Assess serverless SQL warehouse adoption.

    Evidence is gathered from ``system.compute.warehouses``: total warehouse
    count and those running serverless (warehouse_type = 'SERVERLESS' or
    enable_serverless_compute = TRUE). Serverless warehouses start in ~5 seconds
    versus several minutes for classic or pro warehouses.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total": 0, "serverless_count": 0}
        total = int(row.get("total") or 0)
        serverless_count = int(row.get("serverless_count") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{serverless_count} of {total} SQL warehouses use serverless compute "
                    "(warehouse_type='SERVERLESS' or enable_serverless_compute=TRUE)"
                ),
                detail=_SQL,
                rows=[{"total": total, "serverless_count": serverless_count}],
                ref="https://docs.databricks.com/en/compute/sql-warehouse/serverless.html",
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total"]
        serverless_count = row["serverless_count"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No SQL warehouses found in system.compute.warehouses; "
                    "cannot evaluate serverless adoption."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = serverless_count / total
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
                f"{serverless_count} of {total} SQL warehouses ({ratio:.0%}) use serverless "
                f"compute; threshold for 'met' is {_MET_THRESHOLD:.0%}. "
                "Serverless warehouses start in seconds and scale automatically, "
                "reducing cold-start latency for analytics users."
            ),
            sources=evidence,
        )
