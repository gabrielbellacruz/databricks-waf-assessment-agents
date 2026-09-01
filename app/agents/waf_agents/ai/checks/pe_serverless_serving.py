"""Serverless serving for elastic AI performance check (LLM-judged).

Answers:
  AI-PE-01  Use serverless serving for elastic AI performance

Evidence comes from ``system.billing.usage`` filtered to serving and inference
SKUs: GPU-based DBU spend (provisioned throughput, non-serverless) vs total
serving DBUs over the last 30 days.  A high GPU share suggests heavy reliance
on provisioned throughput; serverless (Foundation Model API, pay-per-token)
SKUs carry no GPU suffix.

``Serverless`` is the right default for irregular/bursty workloads; provisioned
throughput is appropriate for sustained high-concurrency.  The ratio is a proxy
for elasticity posture but ``appropriate'' requires manual judgment on workload fit.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  SUM(usage_quantity) AS total_serving_dbus,
  SUM(CASE WHEN sku_name ILIKE '%GPU%' THEN usage_quantity ELSE 0 END) AS gpu_dbus,
  COUNT(DISTINCT sku_name) AS distinct_sku_count
FROM system.billing.usage
WHERE usage_date >= current_date() - INTERVAL 30 DAYS
  AND (
    sku_name ILIKE '%SERVING%'
    OR sku_name ILIKE '%FOUNDATION_MODEL%'
    OR sku_name ILIKE '%INFERENCE%'
  )\
"""

_NOTE = (
    "GPU-based billing SKUs indicate provisioned-throughput endpoints (non-serverless); "
    "Foundation Model API SKUs are pay-per-token (serverless).  The GPU share is "
    "a proxy for how much AI serving relies on dedicated vs elastic compute.  "
    "'Appropriate' use of serverless depends on workload shape (bursty vs sustained) "
    "and latency SLOs — the ratio alone does not determine correctness, and manual "
    "judgment on workload fit is required."
)

_REF = "https://docs.databricks.com/en/machine-learning/foundation-models/index.html"


@register(layer="ai", question_ids=["AI-PE-01"])
class ServerlessServingCheck(Check):
    """Assess serverless-serving adoption via GPU vs non-GPU serving DBU ratio.

    Evidence: system.billing.usage (last 30 days) filtered to serving/inference
    SKUs — total serving DBUs, GPU DBUs, distinct SKU count.  A note records
    that workload fit requires manual judgment.  LLM judges.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        if rows:
            row = rows[0]
            total = float(row.get("total_serving_dbus") or 0)
            gpu = float(row.get("gpu_dbus") or 0)
            sku_count = int(row.get("distinct_sku_count") or 0)
        else:
            total = gpu = 0.0
            sku_count = 0

        if total == 0:
            summary = (
                "No serving/inference billing usage found in system.billing.usage "
                "for the last 30 days — cannot assess serverless vs provisioned split"
            )
        else:
            gpu_pct = round(100.0 * gpu / total, 1)
            serverless = total - gpu
            summary = (
                f"{total:.2f} total serving DBUs (last 30d); "
                f"GPU/provisioned: {gpu:.2f} ({gpu_pct}%), "
                f"non-GPU/serverless: {serverless:.2f} ({100 - gpu_pct}%); "
                f"{sku_count} distinct serving SKU(s)"
            )

        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=[{
                    "total_serving_dbus": total,
                    "gpu_dbus": gpu,
                    "distinct_sku_count": sku_count,
                }],
                ref=_REF,
            ),
            Evidence(kind="note", summary=_NOTE, rows=[], ref=_REF),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
