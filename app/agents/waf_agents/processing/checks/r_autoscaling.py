"""Autoscaling check for transformation workloads (deterministic).

Answers:
  PRO-R-05  Enable autoscaling for transformation workloads

Signal: share of active clusters (delete_time IS NULL) that have autoscaling
enabled, from ``system.compute.clusters``. Autoscaling is inferred when
max_autoscale_workers > min_autoscale_workers (both non-null). Deterministic
ratio vs a threshold -> Medium confidence (proxy: covers all workspace
clusters, not transformation jobs specifically).
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.70
_PARTIAL_THRESHOLD = 0.40

_SQL = (
    "SELECT COUNT(*) AS total, "
    "SUM(CASE WHEN max_autoscale_workers > min_autoscale_workers THEN 1 ELSE 0 END) AS autoscaling "
    "FROM system.compute.clusters "
    "WHERE delete_time IS NULL"
)


@register(layer="processing", question_ids=["PRO-R-05"])
class ProcessingAutoscalingCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total": 0, "autoscaling": 0}
        total = int(row.get("total") or 0)
        autoscaling = int(row.get("autoscaling") or 0)
        return [
            Evidence(
                kind="sql",
                summary=f"{autoscaling} of {total} active clusters have autoscaling enabled",
                detail=_SQL,
                rows=[{"total": total, "autoscaling": autoscaling}],
                ref="https://docs.databricks.com/en/compute/configure.html#autoscaling",
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total, autoscaling = row["total"], row["autoscaling"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No active clusters found in system.compute.clusters; "
                    "cannot evaluate autoscaling coverage for transformation workloads."
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
            confidence=Confidence.MEDIUM,
            score=round(ratio, 4),
            rationale=(
                f"{autoscaling} of {total} active clusters ({ratio:.0%}) have autoscaling enabled "
                f"(max_autoscale_workers > min_autoscale_workers); threshold for 'met' is "
                f"{_MET_THRESHOLD:.0%}. "
                "Note: this is a proxy signal across all workspace clusters, not transformation "
                "jobs specifically — processing-only autoscaling coverage may differ."
            ),
            sources=evidence,
        )
