"""Spot/preemptible instance check for ML training (deterministic).

Answers:
  ML-CO-03  Use spot/preemptible instances for tolerant training

Signal: among active job clusters (``cluster_source = 'JOB'`` and not yet
deleted), the share that have ``aws_attributes.availability`` set to ``SPOT``
or ``SPOT_WITH_FALLBACK``, from ``system.compute.clusters``.

ML training runs that checkpoint their progress can tolerate spot interruptions;
running them on on-demand instances pays a significant premium that is avoidable.
Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.60
_PARTIAL_THRESHOLD = 0.30

_SQL = (
    "SELECT COUNT(*) AS total_job_clusters, "
    "SUM(CASE WHEN aws_attributes.availability IN ('SPOT', 'SPOT_WITH_FALLBACK') "
    "THEN 1 ELSE 0 END) AS spot_clusters "
    "FROM system.compute.clusters "
    "WHERE cluster_source = 'JOB' AND delete_time IS NULL"
)

_REF = "https://docs.databricks.com/en/compute/configure.html#spot-instances"


@register(layer="ml", question_ids=["ML-CO-03"])
class SpotInstancesCheck(Check):
    """Deterministic check for ML-CO-03: spot/preemptible instances for training.

    Counts active job clusters whose ``aws_attributes.availability`` is set to
    SPOT or SPOT_WITH_FALLBACK. All other clusters are treated as on-demand.
    SPOT_WITH_FALLBACK is counted as spot-enabled because it minimises cost
    while providing an on-demand fallback, which is appropriate for most
    tolerant training workloads.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total_job_clusters": 0, "spot_clusters": 0}
        total = int(row.get("total_job_clusters") or 0)
        spot = int(row.get("spot_clusters") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{spot} of {total} active job clusters use spot/preemptible instances"
                ),
                detail=_SQL,
                rows=[{"total_job_clusters": total, "spot_clusters": spot}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total, spot = row["total_job_clusters"], row["spot_clusters"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No active job clusters found; cannot evaluate spot instance coverage "
                    "for ML training runs."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = spot / total
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
                f"{spot} of {total} active job clusters ({ratio:.0%}) are configured "
                f"for spot/preemptible instances (SPOT or SPOT_WITH_FALLBACK); "
                f"threshold for 'met' is {_MET_THRESHOLD:.0%}. On-demand job clusters "
                "for tolerant training runs carry unnecessary cost premium."
            ),
            sources=evidence,
        )
