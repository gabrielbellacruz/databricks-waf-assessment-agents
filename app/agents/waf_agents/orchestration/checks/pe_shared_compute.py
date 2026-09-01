"""Shared-compute reuse check for orchestration (deterministic).

Answers:
  ORC-PE-02  Reuse compute across workflow tasks

Databricks Workflows supports *job-level clusters* — clusters defined once at
the job level and shared by all tasks in a single run.  This avoids spinning up
a fresh cluster per task, reducing cold-start overhead and DBU cost.

Signal: ratio of non-deleted jobs in ``system.lakeflow.jobs`` where
``array_size(job_clusters) > 0`` (job-level shared clusters are declared)
versus total non-deleted jobs.  Jobs with no job-level cluster definition may
use per-task new clusters or existing all-purpose clusters — the latter is also
reuse, but not distinguishable here.

Deterministic count ratio → Confidence.MEDIUM (proxy: job_clusters presence
is necessary but not sufficient; tasks must actually reference those clusters).
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.60
_PARTIAL_THRESHOLD = 0.30

_SQL = """\
SELECT COUNT(*) AS total_jobs,
       SUM(CASE WHEN array_size(job_clusters) > 0 THEN 1 ELSE 0 END) AS jobs_with_shared_clusters
FROM system.lakeflow.jobs
WHERE delete_time IS NULL\
"""

_REF = "https://docs.databricks.com/en/jobs/clusters.html"


@register(layer="orchestration", question_ids=["ORC-PE-02"])
class OrcSharedComputeCheck(Check):
    """Assess shared-compute reuse via job-level cluster definitions in system.lakeflow.jobs.

    Jobs that declare ``job_clusters`` share compute across all tasks in a run,
    avoiding per-task cluster cold-starts.  The ratio of such jobs to all active
    jobs is the compliance proxy.  Note that tasks referencing an existing
    all-purpose cluster are also reusing compute but are counted as non-compliant
    by this metric — Confidence.MEDIUM reflects this limitation.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total_jobs": 0, "jobs_with_shared_clusters": 0}
        total = int(row.get("total_jobs") or 0)
        shared = int(row.get("jobs_with_shared_clusters") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{shared} of {total} active jobs define job-level shared clusters "
                    "(job_clusters array non-empty) — shared compute across tasks"
                ),
                detail=_SQL,
                rows=[{"total_jobs": total, "jobs_with_shared_clusters": shared}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total_jobs"]
        shared = row["jobs_with_shared_clusters"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No active workflow jobs found in system.lakeflow.jobs; "
                    "cannot evaluate shared compute reuse."
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
                f"{shared} of {total} active jobs ({ratio:.0%}) define job-level "
                f"shared clusters (job_clusters non-empty), indicating compute is "
                f"reused across tasks within each run.  Threshold for 'met' is "
                f"{_MET_THRESHOLD:.0%}.  Note: jobs using existing all-purpose "
                f"clusters are not captured by this proxy."
            ),
            sources=evidence,
        )
