"""Overlapping-runs prevention check for orchestration (deterministic).

Answers:
  ORC-R-04  Prevent overlapping runs of the same workflow

Databricks Workflows defaults to a concurrency cap of one run per job, meaning
only one run of a given job executes at a time.  Allowing multiple simultaneous
runs risks resource contention, duplicate writes, or inconsistent state.

The configured cap (``max_concurrent_runs``) is not exposed in system tables, so
this check measures the *observed* behaviour instead: from
``system.lakeflow.job_run_timeline`` it collapses each run to its
[start, end] interval and flags any job whose runs actually overlapped in time
over the last 30 days.  Signal: ratio of jobs with no observed overlapping runs
(protected) versus all jobs that ran in the window.

Deterministic count ratio → Confidence.MEDIUM (observed behaviour: no overlap
seen does not prove the cap is set, but an observed overlap proves concurrency
was allowed).
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.90
_PARTIAL_THRESHOLD = 0.70

_SQL = """\
WITH runs AS (
    SELECT job_id, run_id,
           MIN(period_start_time) AS run_start,
           MAX(period_end_time)   AS run_end
    FROM system.lakeflow.job_run_timeline
    WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS
    GROUP BY job_id, run_id
),
ordered AS (
    SELECT job_id, run_start,
           MAX(run_end) OVER (
               PARTITION BY job_id ORDER BY run_start
               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
           ) AS prev_max_end
    FROM runs
),
overlap AS (
    SELECT DISTINCT job_id FROM ordered
    WHERE prev_max_end IS NOT NULL AND run_start < prev_max_end
)
SELECT (SELECT COUNT(DISTINCT job_id) FROM runs) AS total_jobs,
       (SELECT COUNT(DISTINCT job_id) FROM runs)
           - (SELECT COUNT(*) FROM overlap) AS protected_jobs\
"""

_REF = "https://docs.databricks.com/en/jobs/settings.html#concurrent-runs"


@register(layer="orchestration", question_ids=["ORC-R-04"])
class OrcOverlappingRunsCheck(Check):
    """Assess concurrent-run protection from observed run intervals in job_run_timeline.

    The configured concurrency cap is not exposed in system tables, so this check
    collapses each run to its [start, end] interval and flags any job whose runs
    overlapped in time over the last 30 days.  Jobs with no observed overlap are
    treated as protected; the check surfaces the fraction that did overlap.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total_jobs": 0, "protected_jobs": 0}
        total = int(row.get("total_jobs") or 0)
        protected = int(row.get("protected_jobs") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{protected} of {total} jobs that ran in the last 30 days had no "
                    "overlapping runs — protected from accidental concurrency"
                ),
                detail=_SQL,
                rows=[{"total_jobs": total, "protected_jobs": protected}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total_jobs"]
        protected = row["protected_jobs"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No job runs found in system.lakeflow.job_run_timeline for the last "
                    "30 days; cannot evaluate overlapping-run protection."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = protected / total
        if ratio >= _MET_THRESHOLD:
            verdict = Verdict.MET
        elif ratio >= _PARTIAL_THRESHOLD:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.NOT_MET

        unprotected = total - protected
        return Finding(
            question_id=question.id,
            pillar_id=question.pillar_id,
            verdict=verdict,
            confidence=Confidence.MEDIUM,
            score=round(ratio, 4),
            rationale=(
                f"{protected} of {total} jobs that ran in the last 30 days ({ratio:.0%}) "
                f"had no overlapping runs and are protected against accidental "
                f"concurrency.  {unprotected} job(s) had runs that actually overlapped "
                f"in time and should be reviewed.  Threshold for 'met' is "
                f"{_MET_THRESHOLD:.0%}.  Note: observed from run intervals — the "
                f"configured max_concurrent_runs cap is not exposed in system tables."
            ),
            sources=evidence,
        )
