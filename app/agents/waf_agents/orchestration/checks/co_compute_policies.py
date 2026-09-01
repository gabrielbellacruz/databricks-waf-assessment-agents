"""Compute-policy coverage check for workflow clusters (deterministic).

Answers:
  ORC-CO-04  Use compute policies to bound workflow cost

Signal: the share of active job clusters (``cluster_source = 'JOB'``) that
have a compute policy attached (``policy_id IS NOT NULL``), from
``system.compute.clusters``.  Policies enforce max-size caps, instance-type
restrictions, and cost controls on the clusters workflows create.

Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.70
_PARTIAL_THRESHOLD = 0.40

_SQL = (
    "SELECT COUNT(*) AS total_job_clusters, "
    "SUM(CASE WHEN policy_id IS NOT NULL AND policy_id != '' THEN 1 ELSE 0 END) "
    "AS policy_bound "
    "FROM system.compute.clusters "
    "WHERE cluster_source = 'JOB' "
    "AND delete_time IS NULL"
)

_REF = "https://docs.databricks.com/en/administration-guide/clusters/policies.html"


@register(layer="orchestration", question_ids=["ORC-CO-04"])
class OrcComputePoliciesCheck(Check):
    """Deterministic check for ORC-CO-04: compute-policy coverage on job clusters.

    A job cluster without a policy has no enforced bound on its size or
    instance type, so a misconfigured workflow can spin up arbitrarily large
    clusters and drive unexpected cost.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total_job_clusters": 0, "policy_bound": 0}
        total = int(row.get("total_job_clusters") or 0)
        policy_bound = int(row.get("policy_bound") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{policy_bound} of {total} active job clusters have a compute policy attached"
                ),
                detail=_SQL,
                rows=[{"total_job_clusters": total, "policy_bound": policy_bound}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total_job_clusters"]
        policy_bound = row["policy_bound"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No active job clusters found in system.compute.clusters; "
                    "cannot evaluate compute-policy coverage."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = policy_bound / total
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
                f"{policy_bound} of {total} active job clusters ({ratio:.0%}) have a compute "
                f"policy attached; threshold for 'met' is {_MET_THRESHOLD:.0%}. "
                "Clusters without a policy have no enforced size or cost bounds."
            ),
            sources=evidence,
        )
