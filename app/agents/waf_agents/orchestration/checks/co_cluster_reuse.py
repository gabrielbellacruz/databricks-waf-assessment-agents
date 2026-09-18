"""Cluster reuse across tasks check (deterministic).

Answers:
  ORC-CO-02  Share clusters across tasks to reduce cost

Signal: among multi-task jobs that ran in the last 30 days, the fraction that
reused a cluster across tasks in at least one run.  Reuse is inferred when
``COUNT(DISTINCT cluster_id) < COUNT(DISTINCT task_key)`` within a single
(job_id, job_run_id) group in ``system.lakeflow.job_task_run_timeline``.  The
per-task cluster id lives in that table's ``compute`` array
(``array<struct<type, cluster_id, warehouse_id>>``), which is exploded before
counting.

Deterministic ratio vs a threshold -> Medium confidence (proxy: we observe
run behaviour rather than reading the job's cluster-key configuration directly).
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.70
_PARTIAL_THRESHOLD = 0.40
_WINDOW_DAYS = 30

_SQL = (
    "SELECT "
    "COUNT(DISTINCT job_id) AS total_multi_task_jobs, "
    "COUNT(DISTINCT CASE WHEN cluster_count < task_count THEN job_id END) AS sharing_jobs "
    "FROM ("
    "    SELECT job_id, job_run_id, "
    "           COUNT(DISTINCT task_key) AS task_count, "
    "           COUNT(DISTINCT c.cluster_id) AS cluster_count "
    "    FROM system.lakeflow.job_task_run_timeline "
    "         LATERAL VIEW explode(compute) t AS c "
    f"   WHERE period_start_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS "
    "      AND c.cluster_id IS NOT NULL "
    "    GROUP BY job_id, job_run_id "
    "    HAVING COUNT(DISTINCT task_key) > 1"
    ") sub"
)

_REF = "https://docs.databricks.com/en/workflows/jobs/configure-workflow-tasks.html"


@register(layer="orchestration", question_ids=["ORC-CO-02"])
class OrcClusterReuseCheck(Check):
    """Deterministic check for ORC-CO-02: cluster sharing across workflow tasks.

    Among multi-task jobs active in the last 30 days, measures the fraction
    that had at least one run where multiple tasks shared a cluster.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total_multi_task_jobs": 0, "sharing_jobs": 0}
        total = int(row.get("total_multi_task_jobs") or 0)
        sharing = int(row.get("sharing_jobs") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{sharing} of {total} multi-task jobs (last {_WINDOW_DAYS}d) "
                    "reused a cluster across tasks in at least one run"
                ),
                detail=_SQL,
                rows=[{"total_multi_task_jobs": total, "sharing_jobs": sharing}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total_multi_task_jobs"]
        sharing = row["sharing_jobs"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No multi-task workflow runs found in the window; "
                    "cannot evaluate cluster sharing."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = sharing / total
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
                f"{sharing} of {total} multi-task jobs ({ratio:.0%}) reused a cluster "
                f"across tasks in the last {_WINDOW_DAYS} days; threshold for 'met' is "
                f"{_MET_THRESHOLD:.0%}. "
                "Note: inferred from run behaviour in system.lakeflow.job_task_run_timeline — "
                "cluster-key configuration itself is not directly readable by this agent."
            ),
            sources=evidence,
        )
