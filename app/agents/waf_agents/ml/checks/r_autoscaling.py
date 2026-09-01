"""Autoscaling for training and serving (deterministic).

Answers:
  ML-R-05  Autoscale training and serving to demand

Signal: share of active clusters (delete_time IS NULL) that have
autoscaling enabled, from ``system.compute.clusters``. Autoscaling is
inferred when max_autoscale_workers > min_autoscale_workers (both
non-null). Deterministic ratio vs a threshold -> HIGH confidence for the
ratio itself; MEDIUM overall because the signal covers all workspace
clusters, not ML-training clusters specifically, and serving-endpoint
scale-to-zero config is not exposed in system tables.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.70
_PARTIAL_THRESHOLD = 0.40

_SQL = (
    "SELECT COUNT(*) AS total, "
    "SUM(CASE WHEN max_autoscale_workers > min_autoscale_workers THEN 1 ELSE 0 END) "
    "AS autoscaling_enabled "
    "FROM system.compute.clusters "
    "WHERE delete_time IS NULL"
)

_NOTE = (
    "Cluster autoscaling coverage is only a proxy: serving-endpoint scale-to-zero "
    "and provisioned-throughput configuration are endpoint API settings not exposed "
    "in system tables. Manual confirmation of serving autoscaling is needed."
)


@register(layer="ml", question_ids=["ML-R-05"])
class MlAutoscalingCheck(Check):
    """Assess autoscaling adoption via the active-cluster autoscale ratio.

    Deterministic: ratio = autoscaling_enabled / total active clusters.
    Thresholds: MET >= 70%, PARTIAL >= 40%, else NOT_MET. An empty
    cluster roster yields UNKNOWN / LOW. A note evidence records that
    serving-endpoint scale-to-zero is not observable from system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total": 0, "autoscaling_enabled": 0}
        total = int(row.get("total") or 0)
        autoscaling = int(row.get("autoscaling_enabled") or 0)
        return [
            Evidence(
                kind="sql",
                summary=f"{autoscaling} of {total} active clusters have autoscaling enabled",
                detail=_SQL,
                rows=[{"total": total, "autoscaling_enabled": autoscaling}],
                ref="https://docs.databricks.com/en/compute/configure.html#autoscaling",
            ),
            Evidence(
                kind="note",
                summary=_NOTE,
                rows=[],
                ref="https://docs.databricks.com/en/machine-learning/model-serving/index.html",
            ),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total"]
        autoscaling = row["autoscaling_enabled"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No active clusters found in system.compute.clusters; "
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
            confidence=Confidence.MEDIUM,
            score=round(ratio, 4),
            rationale=(
                f"{autoscaling} of {total} active clusters ({ratio:.0%}) have autoscaling "
                f"enabled (max_autoscale_workers > min_autoscale_workers); threshold for "
                f"'met' is {_MET_THRESHOLD:.0%}. "
                "Note: this covers all workspace clusters — ML-training-specific coverage "
                "and serving-endpoint scale-to-zero are not directly observable and "
                "require manual confirmation."
            ),
            sources=evidence,
        )
