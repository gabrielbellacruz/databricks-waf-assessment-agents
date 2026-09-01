"""Cluster auto-termination check (deterministic).

Answers:
  ING-CO-03  Auto-terminate ingestion compute when idle

Signal: among interactive clusters (cluster_source IN ('UI','API') and not yet
deleted), the share configured with a non-zero ``auto_termination_minutes`` value,
from ``system.compute.clusters``. Job clusters are ephemeral and excluded from
the denominator. Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.90
_PARTIAL_THRESHOLD = 0.50


@register(layer="ingestion", question_ids=["ING-CO-03"])
class ClusterAutoterminationCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        sql = (
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN auto_termination_minutes > 0 THEN 1 ELSE 0 END) AS auto_term "
            "FROM system.compute.clusters "
            "WHERE cluster_source IN ('UI','API') AND delete_time IS NULL"
        )
        rows = ctx.sql.query(sql)
        row = rows[0] if rows else {"total": 0, "auto_term": 0}
        total = int(row.get("total") or 0)
        auto_term = int(row.get("auto_term") or 0)
        return [
            Evidence(
                kind="sql",
                summary=f"{auto_term} of {total} interactive clusters have auto-termination set",
                detail=sql,
                rows=[{"total": total, "auto_term": auto_term}],
                ref="https://docs.databricks.com/en/compute/cluster-config-best-practices.html",
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total, auto_term = row["total"], row["auto_term"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale="No interactive clusters to evaluate auto-termination coverage.",
                sources=evidence,
                auto_assessable=True,
            )

        ratio = auto_term / total
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
                f"{auto_term} of {total} interactive clusters ({ratio:.0%}) have auto-termination "
                f"configured; threshold for 'met' is {_MET_THRESHOLD:.0%}. Clusters without "
                "auto-termination continue to run and accrue cost when idle."
            ),
            sources=evidence,
        )
