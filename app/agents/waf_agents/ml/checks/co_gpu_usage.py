"""GPU usage appropriateness check (LLM-judged).

Answers:
  ML-CO-01  Only use GPUs for workloads that need them

Signal: ``system.billing.usage`` over the last 30 days, split by whether the
SKU carries 'GPU' (GPU compute) and whether it is 'ALL_PURPOSE' or job/serverless.
A workspace that routes most GPU DBUs through job clusters is using GPUs
deliberately for training runs; a workspace with most GPU DBUs on all-purpose
clusters likely has developers running interactive sessions on expensive GPU
instances unnecessarily.

Because "this workload needs a GPU" is a judgment call (billing data alone
can't confirm what each job was doing), a human-readable summary of the signal
is passed to the LLM judge which returns a structured verdict.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 30

_SQL = (
    "SELECT "
    "SUM(usage_quantity) AS total_compute_dbus, "
    "SUM(CASE WHEN sku_name ILIKE '%GPU%' THEN usage_quantity ELSE 0 END) AS gpu_dbus, "
    "SUM(CASE WHEN sku_name ILIKE '%GPU%' AND sku_name ILIKE '%ALL_PURPOSE%' "
    "THEN usage_quantity ELSE 0 END) AS all_purpose_gpu_dbus, "
    "SUM(CASE WHEN sku_name ILIKE '%GPU%' AND sku_name NOT ILIKE '%ALL_PURPOSE%' "
    "THEN usage_quantity ELSE 0 END) AS job_gpu_dbus "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "AND sku_name ILIKE '%COMPUTE%'"
)

_NOTE = (
    "Billing data alone cannot confirm whether each GPU workload actually required "
    "a GPU (e.g., deep-learning model training) vs a CPU-only task (e.g., data "
    "preprocessing, hyperparameter search on a trivial model). A high share of "
    "all-purpose GPU DBUs is the clearest cost-optimization risk: developers "
    "attaching GPU clusters for interactive work they could do on CPU instances. "
    "Manual review is recommended to confirm that GPU-attached clusters are reserved "
    "for GPU-accelerated workloads."
)

_REF = "https://docs.databricks.com/en/machine-learning/train-model/gpu.html"


@register(layer="ml", question_ids=["ML-CO-01"])
class GpuUsageCheck(Check):
    """Assess GPU-usage appropriateness from billing DBU breakdown.

    Two evidence pieces are collected: a SQL evidence with GPU vs non-GPU
    DBU totals and the ALL_PURPOSE vs job-cluster GPU split; and a note
    evidence acknowledging the limitation that billing data cannot confirm
    whether each GPU workload truly required GPU acceleration.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {}
        total_compute = float(row.get("total_compute_dbus") or 0)
        gpu_dbus = float(row.get("gpu_dbus") or 0)
        all_purpose_gpu = float(row.get("all_purpose_gpu_dbus") or 0)
        job_gpu = float(row.get("job_gpu_dbus") or 0)

        if total_compute == 0:
            sql_summary = (
                f"No compute billing usage found in the last {_WINDOW_DAYS} days; "
                "cannot evaluate GPU usage appropriateness."
            )
        elif gpu_dbus == 0:
            sql_summary = (
                f"No GPU compute DBUs found in the last {_WINDOW_DAYS} days "
                f"(total compute: {total_compute:.1f} DBUs); GPU instances appear unused."
            )
        else:
            gpu_pct = gpu_dbus / total_compute
            ap_pct = all_purpose_gpu / gpu_dbus if gpu_dbus > 0 else 0.0
            job_pct = job_gpu / gpu_dbus if gpu_dbus > 0 else 0.0
            sql_summary = (
                f"GPU DBUs: {gpu_dbus:.1f} of {total_compute:.1f} total compute DBUs "
                f"({gpu_pct:.0%}); of GPU DBUs: {all_purpose_gpu:.1f} ({ap_pct:.0%}) "
                f"are all-purpose, {job_gpu:.1f} ({job_pct:.0%}) are job/serverless "
                f"(last {_WINDOW_DAYS}d)."
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=sql_summary,
            detail=_SQL,
            rows=[
                {
                    "total_compute_dbus": total_compute,
                    "gpu_dbus": gpu_dbus,
                    "all_purpose_gpu_dbus": all_purpose_gpu,
                    "job_gpu_dbus": job_gpu,
                }
            ],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            ref=_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
