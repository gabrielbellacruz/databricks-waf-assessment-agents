"""Consistent ML compute check (LLM-judged).

Answers:
  ML-IU-05  Use consistent, pre-defined compute for ML

Signals:
  * ``system.billing.usage`` — SKU distribution for ML-related compute (ML and
    JOBS_COMPUTE SKUs) in the last 90 days. A narrow SKU distribution suggests compute
    standardisation; a wide distribution may indicate ad-hoc configuration.
  * ``system.billing.usage`` — fraction of ML-related billing records that carry a
    usage policy ID (``usage_metadata.usage_policy_id IS NOT NULL``). Usage policies
    (formerly cluster/budget policies) enforce pre-defined compute configurations and
    are the primary mechanism for compute consistency in Databricks.
  * Note: the specific instance type and Databricks Runtime version enforced by cluster
    policies are stored in the policy definition (workspace REST API), not in system
    tables. A workspace that enforces consistency via policies but has not tagged its
    policy IDs in billing may appear as inconsistent here.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 90

# ML-related billing SKU distribution.
_ML_SKU_DIST_SQL = (
    "SELECT sku_name AS ml_compute_sku, COUNT(*) AS sku_count "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "  AND (sku_name ILIKE '%ML%' OR sku_name ILIKE '%JOBS%') "
    "GROUP BY sku_name "
    "ORDER BY sku_count DESC "
    "LIMIT 15"
)

# Fraction of ML billing rows with a cluster policy assigned.
_POLICY_ADOPTION_SQL = (
    "SELECT COUNT(*) AS total_ml_rows, "
    "SUM(CASE WHEN usage_metadata.usage_policy_id IS NOT NULL THEN 1 ELSE 0 END) "
    "  AS distinct_policies "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "  AND (sku_name ILIKE '%ML%' OR sku_name ILIKE '%JOBS%')"
)

_NOTE = (
    "Cluster policy definitions (allowed instance types, DBR versions, autoscaling bounds) "
    "are in the workspace REST API, not in system tables. A workspace that enforces compute "
    "consistency via policies but does not record policy IDs in billing may appear "
    "inconsistent here. Per-team ML runtime standards enforced outside Databricks (e.g. via "
    "container images or CI/CD) are also not observable. Manual review of cluster policy "
    "configuration is recommended."
)

_REF = (
    "https://docs.databricks.com/en/administration-guide/clusters/policies.html"
)


@register(layer="ml", question_ids=["ML-IU-05"])
class MlConsistentComputeCheck(Check):
    """LLM-judged check for ML-IU-05: consistent, pre-defined compute for ML."""

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        sku_rows = ctx.sql.query(_ML_SKU_DIST_SQL)
        policy_rows = ctx.sql.query(_POLICY_ADOPTION_SQL)

        prow = policy_rows[0] if policy_rows else {}
        total_ml_rows = int(prow.get("total_ml_rows") or 0)
        distinct_policies = int(prow.get("distinct_policies") or 0)

        sku_evidence = Evidence(
            kind="sql",
            summary=(
                f"{len(sku_rows)} distinct ML/JOBS SKU type(s) observed in the last "
                f"{_WINDOW_DAYS} days (top-15 shown)"
            ),
            detail=_ML_SKU_DIST_SQL,
            rows=sku_rows[:15],
            ref=_REF,
        )
        policy_evidence = Evidence(
            kind="sql",
            summary=(
                f"{distinct_policies} of {total_ml_rows} ML/JOBS billing records "
                f"(last {_WINDOW_DAYS} days) have a cluster policy ID assigned"
            ),
            detail=_POLICY_ADOPTION_SQL,
            rows=[
                {
                    "total_ml_rows": total_ml_rows,
                    "distinct_policies": distinct_policies,
                }
            ],
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )
        return [sku_evidence, policy_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
