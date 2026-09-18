"""Hardware matching for ML workloads check (LLM-judged).

Answers:
  ML-PE-01  Match hardware to the ML workload

Whether hardware is well-matched to each ML workload requires knowing the
workload type (deep-learning training, NLP inference, classical ML, etc.),
which is not exposed in system tables. The observable proxies are:
  1. GPU billing SKUs in ``system.billing.usage`` — GPU DBUs indicate at
     least some GPU-bound workloads are using GPU hardware.
  2. Cluster node_type_id in ``system.compute.clusters`` — instance names
     containing 'GPU' or common GPU families (g4dn, p3, a100, etc.) confirm
     GPU cluster definitions.
The LLM judge weighs both pieces and notes that absence of GPU spend does
not necessarily mean hardware is mismatched (not every ML workload benefits
from GPU).
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

# Distinct needle for FakeSqlClient: "GPU SKUs"
_BILLING_SQL = """\
SELECT
  SUM(usage_quantity) AS total_dbus,
  SUM(CASE WHEN sku_name ILIKE '%GPU%' THEN usage_quantity ELSE 0 END) AS gpu_dbus
FROM system.billing.usage
WHERE usage_date >= current_date() - INTERVAL 30 DAYS
  AND sku_name ILIKE '%COMPUTE%'\
"""

# Distinct needle: "node_type_id"
_CLUSTER_SQL = """\
SELECT
  worker_node_type AS node_type_id,
  COUNT(*) AS cluster_count
FROM system.compute.clusters
WHERE delete_time IS NULL
GROUP BY worker_node_type
ORDER BY cluster_count DESC
LIMIT 25\
"""

_NOTE = (
    "Hardware matching requires knowing each workload's type (deep-learning training, "
    "inference, classical ML, batch scoring) which is not exposed in system tables. "
    "GPU billing DBUs confirm GPU hardware is used somewhere but cannot determine "
    "whether non-GPU workloads that should use GPU are missing out, or whether GPU "
    "resources are oversized. Manual review of job/cluster configurations is needed."
)

_REF = "https://docs.databricks.com/en/compute/gpu.html"


@register(layer="ml", question_ids=["ML-PE-01"])
class MlHardwareMatchingCheck(Check):
    """Assess hardware-to-workload matching via GPU billing and cluster node types.

    Evidence is gathered from system.billing.usage (GPU SKU share, last 30 days)
    and system.compute.clusters (active cluster node_type_id distribution). A
    note evidence records that hardware matching is a judgment call requiring
    workload-type knowledge not available from system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        evidence: list[Evidence] = []

        # 1. GPU billing share
        billing_rows = ctx.sql.query(_BILLING_SQL)
        if billing_rows:
            row = billing_rows[0]
            total = float(row.get("total_dbus") or 0)
            gpu = float(row.get("gpu_dbus") or 0)
        else:
            total = gpu = 0.0

        if total > 0:
            gpu_pct = round(100.0 * gpu / total, 1)
            billing_summary = (
                f"{gpu:.2f} of {total:.2f} compute DBUs ({gpu_pct}%) in the last 30 days "
                f"are on GPU SKUs"
            )
        else:
            billing_summary = (
                "No compute billing usage found in the last 30 days — "
                "cannot assess GPU hardware adoption"
            )

        evidence.append(
            Evidence(
                kind="sql",
                summary=billing_summary,
                detail=_BILLING_SQL,
                rows=[{"total_dbus": total, "gpu_dbus": gpu}],
                ref="https://docs.databricks.com/en/admin/system-tables/billing.html",
            )
        )

        # 2. Cluster node types
        cluster_rows = ctx.sql.query(_CLUSTER_SQL)
        gpu_node_count = sum(
            int(r.get("cluster_count") or 0)
            for r in cluster_rows
            if any(
                kw in str(r.get("node_type_id", "")).upper()
                for kw in ("GPU", "G4DN", "G5", "P3", "P4", "A100", "A10", "T4")
            )
        )
        total_nodes = sum(int(r.get("cluster_count") or 0) for r in cluster_rows)

        if cluster_rows:
            cluster_summary = (
                f"{total_nodes} active cluster definitions; "
                f"{gpu_node_count} use GPU-class node types"
            )
        else:
            cluster_summary = (
                "No active clusters found in system.compute.clusters"
            )

        evidence.append(
            Evidence(
                kind="sql",
                summary=cluster_summary,
                detail=_CLUSTER_SQL,
                rows=cluster_rows[:10],
                ref="https://docs.databricks.com/en/compute/gpu.html",
            )
        )

        evidence.append(
            Evidence(
                kind="note",
                summary=_NOTE,
                rows=[],
                ref=_REF,
            )
        )

        return evidence

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
