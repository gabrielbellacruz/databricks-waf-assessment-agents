"""Distributed training usage check (LLM-judged).

Answers:
  ML-PE-02  Use distributed training where beneficial

Whether distributed training frameworks (Horovod, TorchDistributed,
DeepSpeed, Ray Train, Spark ML) are actually in use cannot be determined
from system tables. The observable proxy is the presence of large multi-node
clusters in ``system.compute.clusters``: clusters with many workers are a
necessary (but not sufficient) condition for distributed training. Long
job-run durations in ``system.lakeflow.job_run_timeline`` together with
multi-node cluster definitions suggest training is at least happening at
scale. A limitation note accompanies all evidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_LARGE_CLUSTER_THRESHOLD = 4  # workers; clusters above this are "large"

# Distinct needle: "max_autoscale_workers" (unique to this check)
_CLUSTER_SQL = f"""\
SELECT
  COUNT(*) AS total_clusters,
  SUM(
    CASE WHEN COALESCE(max_autoscale_workers, worker_count, 0) > {_LARGE_CLUSTER_THRESHOLD}
    THEN 1 ELSE 0 END
  ) AS large_clusters,
  MAX(COALESCE(max_autoscale_workers, worker_count, 0)) AS max_workers_seen
FROM system.compute.clusters
WHERE delete_time IS NULL\
"""

# Distinct needle: "long_runs" (unique to this check)
_JOB_SQL = """\
SELECT
  COUNT(*) AS total_runs,
  SUM(
    CASE WHEN TIMESTAMPDIFF(MINUTE, period_start_time, period_end_time) > 30 THEN 1 ELSE 0 END
  ) AS long_runs
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS
  AND period_end_time IS NOT NULL\
"""

_NOTE = (
    "Whether distributed training frameworks (Horovod, TorchDistributed, DeepSpeed, "
    "Ray Train, Spark ML) are actually used cannot be determined from system tables. "
    "Large multi-node clusters and long job durations are only a proxy — the actual "
    "training framework and whether parallelism is exploited require manual review of "
    "notebook/job code and MLflow experiment metadata."
)

_REF = "https://docs.databricks.com/en/machine-learning/train-model/distributed-training/index.html"


@register(layer="ml", question_ids=["ML-PE-02"])
class MlDistributedTrainingCheck(Check):
    """Assess distributed training adoption via cluster size and job duration.

    Evidence is gathered from system.compute.clusters (large-cluster count,
    last 30 days) and system.lakeflow.job_run_timeline (long-run count,
    last 30 days). A note evidence records that framework choice is not
    observable from system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        evidence: list[Evidence] = []

        # 1. Large-cluster signal
        cluster_rows = ctx.sql.query(_CLUSTER_SQL)
        if cluster_rows:
            row = cluster_rows[0]
            total_clusters = int(row.get("total_clusters") or 0)
            large_clusters = int(row.get("large_clusters") or 0)
            max_workers = int(row.get("max_workers_seen") or 0)
        else:
            total_clusters = large_clusters = max_workers = 0

        if total_clusters > 0:
            cluster_summary = (
                f"{large_clusters} of {total_clusters} active clusters have >"
                f"{_LARGE_CLUSTER_THRESHOLD} workers (max workers seen: {max_workers})"
            )
        else:
            cluster_summary = "No active clusters found in system.compute.clusters"

        evidence.append(
            Evidence(
                kind="sql",
                summary=cluster_summary,
                detail=_CLUSTER_SQL,
                rows=[
                    {
                        "total_clusters": total_clusters,
                        "large_clusters": large_clusters,
                        "max_workers_seen": max_workers,
                    }
                ],
                ref="https://docs.databricks.com/en/compute/configure.html",
            )
        )

        # 2. Long-running job signal
        job_rows = ctx.sql.query(_JOB_SQL)
        if job_rows:
            row = job_rows[0]
            total_runs = int(row.get("total_runs") or 0)
            long_runs = int(row.get("long_runs") or 0)
        else:
            total_runs = long_runs = 0

        if total_runs > 0:
            long_pct = round(100.0 * long_runs / total_runs, 1)
            job_summary = (
                f"{long_runs} of {total_runs} job runs ({long_pct}%) exceeded 30 min "
                "in the last 30 days — may indicate large training workloads"
            )
        else:
            job_summary = (
                "No completed job runs found in system.lakeflow.job_run_timeline "
                "for the last 30 days"
            )

        evidence.append(
            Evidence(
                kind="sql",
                summary=job_summary,
                detail=_JOB_SQL,
                rows=[{"total_runs": total_runs, "long_runs": long_runs}],
                ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
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
