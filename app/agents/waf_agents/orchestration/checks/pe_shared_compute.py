"""Shared-compute reuse check for orchestration (deterministic).

Answers:
  ORC-PE-02  Reuse compute across workflow tasks

Databricks Workflows supports *job-level clusters* — clusters defined once at
the job level and shared by all tasks in a single run.  This avoids spinning up
a fresh cluster per task, reducing cold-start overhead and DBU cost.

Signal: among multi-task job runs in the last 30 days, the fraction that reused
compute across tasks — i.e. fewer distinct cluster ids than distinct task keys
within a single (job_id, job_run_id) group in
``system.lakeflow.job_task_run_timeline``.  The per-task cluster id lives in
that table's ``compute`` array (``array<struct<type, cluster_id,
warehouse_id>>``), which is exploded before counting.  This observes actual
compute reuse at run time rather than reading the job's cluster configuration.

Deterministic count ratio → Confidence.MEDIUM (proxy: observed from run
behaviour; tasks on existing all-purpose clusters are also reuse and are
captured, but serverless tasks with no cluster id are excluded).
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.60
_PARTIAL_THRESHOLD = 0.30

_SQL = """\
SELECT COUNT(*) AS total_multi_task_runs,
       SUM(CASE WHEN cluster_count < task_count THEN 1 ELSE 0 END) AS shared_compute_runs
FROM (
    SELECT job_id, job_run_id,
           COUNT(DISTINCT task_key) AS task_count,
           COUNT(DISTINCT c.cluster_id) AS cluster_count
    FROM system.lakeflow.job_task_run_timeline
         LATERAL VIEW explode(compute) t AS c
    WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS
      AND c.cluster_id IS NOT NULL
    GROUP BY job_id, job_run_id
    HAVING COUNT(DISTINCT task_key) > 1
) sub\
"""

_REF = "https://docs.databricks.com/en/jobs/clusters.html"


@register(layer="orchestration", question_ids=["ORC-PE-02"])
class OrcSharedComputeCheck(Check):
    """Assess shared-compute reuse from run behaviour in system.lakeflow.job_task_run_timeline.

    Among multi-task job runs in the last 30 days, measures the fraction that
    used fewer distinct clusters than tasks — i.e. reused compute across tasks
    within a run.  Serverless tasks with no cluster id are excluded, so this is
    a lower-bound proxy — Confidence.MEDIUM reflects that limitation.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total_multi_task_runs": 0, "shared_compute_runs": 0}
        total = int(row.get("total_multi_task_runs") or 0)
        shared = int(row.get("shared_compute_runs") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{shared} of {total} multi-task job runs (last 30d) reused a "
                    "cluster across tasks — shared compute within the run"
                ),
                detail=_SQL,
                rows=[{"total_multi_task_runs": total, "shared_compute_runs": shared}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total_multi_task_runs"]
        shared = row["shared_compute_runs"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No multi-task job runs found in system.lakeflow.job_task_run_timeline "
                    "for the last 30 days; cannot evaluate shared compute reuse."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = shared / total
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
                f"{shared} of {total} multi-task job runs ({ratio:.0%}) reused a "
                f"cluster across tasks within the run, indicating shared compute.  "
                f"Threshold for 'met' is {_MET_THRESHOLD:.0%}.  Note: serverless "
                f"tasks with no cluster id are excluded, so this is a lower bound."
            ),
            sources=evidence,
        )
