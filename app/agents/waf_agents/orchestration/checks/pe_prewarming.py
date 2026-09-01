"""Compute prewarming check for orchestration (LLM-judged).

Answers:
  ORC-PE-03  Account for compute prewarming in schedules

Cluster cold-start (typically 3–5 minutes for job clusters) adds latency
between a workflow's scheduled trigger time and the first task actually running.
Mitigations include instance pools, cluster pre-warming, or scheduling jobs
earlier than the SLA deadline to absorb warm-up time.

System-table observability is limited:
  - ``system.compute.clusters`` shows active clusters but not whether they
    are pool-backed or how long each warm-up took.
  - ``system.lakeflow.job_run_timeline`` shows run start/end times but does
    not separate "cluster provisioning" from "task execution" duration.

Evidence is gathered as proxies: the count of active clusters and any pools
in the workspace.  A note records the measurement gap explicitly.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_CLUSTERS = """\
SELECT COUNT(*) AS total_active_clusters,
       SUM(CASE WHEN max_autoscale_workers > min_autoscale_workers THEN 1 ELSE 0 END)
           AS autoscaling_clusters
FROM system.compute.clusters
WHERE delete_time IS NULL\
"""

_SQL_RUNS = """\
SELECT COUNT(DISTINCT run_id) AS total_runs,
       AVG(CAST(period_end_time AS DOUBLE) - CAST(period_start_time AS DOUBLE))
           AS avg_run_seconds
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS
  AND period_end_time IS NOT NULL\
"""

_NOTE = (
    "Compute prewarming configuration — instance pools, keep-alive settings, and "
    "scheduled warm-up jobs — is not exposed in system tables.  The active cluster "
    "count and run duration averages are weak proxies only.  Manual review of cluster "
    "pool configuration and job schedule SLA buffers is required to confirm that "
    "cold-start time is accounted for."
)

_REF = "https://docs.databricks.com/en/compute/pool-overview.html"


@register(layer="orchestration", question_ids=["ORC-PE-03"])
class OrcPrewarmingCheck(Check):
    """Assess compute prewarming readiness via cluster count and run duration signals.

    Evidence is gathered from:
      - ``system.compute.clusters``          (active cluster count, autoscaling)
      - ``system.lakeflow.job_run_timeline`` (avg run duration as cold-start proxy)
    A note records that actual prewarming configuration is not system-table visible.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        # --- evidence 1: active cluster count and autoscaling ---
        cluster_rows = ctx.sql.query(_SQL_CLUSTERS)
        cluster_row = cluster_rows[0] if cluster_rows else {}
        total_clusters = int(cluster_row.get("total_active_clusters") or 0)
        autoscaling = int(cluster_row.get("autoscaling_clusters") or 0)

        ev_clusters = Evidence(
            kind="sql",
            summary=(
                f"{total_clusters} active clusters; {autoscaling} with autoscaling enabled "
                "(pool-backed clusters not distinguishable from system tables)"
            ),
            detail=_SQL_CLUSTERS,
            rows=[{"total_active_clusters": total_clusters, "autoscaling_clusters": autoscaling}],
            ref=_REF,
        )

        # --- evidence 2: avg run duration (cold-start proxy) ---
        run_rows = ctx.sql.query(_SQL_RUNS)
        run_row = run_rows[0] if run_rows else {}
        total_runs = int(run_row.get("total_runs") or 0)
        avg_raw = run_row.get("avg_run_seconds")
        avg_secs = round(float(avg_raw), 1) if avg_raw is not None else None

        if total_runs > 0:
            dur_str = f", avg duration {avg_secs}s" if avg_secs is not None else ""
            run_summary = (
                f"{total_runs} workflow runs over the last 30 days{dur_str} "
                "(duration includes cluster provisioning time)"
            )
        else:
            run_summary = "No workflow runs found in job_run_timeline for the last 30 days"

        ev_runs = Evidence(
            kind="sql",
            summary=run_summary,
            detail=_SQL_RUNS,
            rows=[{"total_runs": total_runs, "avg_run_seconds": avg_secs}],
            ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [ev_clusters, ev_runs, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
