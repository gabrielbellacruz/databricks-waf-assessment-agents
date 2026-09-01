"""Workflow execution audit check (deterministic).

Answers:
  ORC-DG-04  Audit workflow executions

Signal: the share of active jobs that have at least one run recorded in
``system.lakeflow.job_run_timeline`` within the last 90 days.  The presence
of run history is a direct indicator that executions are captured in the
platform's audit trail.  Jobs with no recent runs cannot be confirmed as
audited.

Deterministic ratio vs a threshold -> HIGH confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.80
_PARTIAL_THRESHOLD = 0.40
_WINDOW_DAYS = 90

_SQL_TOTAL = (
    "SELECT COUNT(*) AS total_jobs "
    "FROM system.lakeflow.jobs "
    "WHERE delete_time IS NULL"
)

_SQL_AUDITED = (
    "SELECT COUNT(DISTINCT job_id) AS jobs_with_runs "
    "FROM system.lakeflow.job_run_timeline "
    f"WHERE period_start_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS"
)

_REF = "https://docs.databricks.com/en/admin/account-settings/audit-log.html"


@register(layer="orchestration", question_ids=["ORC-DG-04"])
class WorkflowAuditCheck(Check):
    """Deterministic check for ORC-DG-04: audit of workflow executions.

    A job is counted as 'audited' when at least one execution appears in
    system.lakeflow.job_run_timeline within the last 90 days. Jobs that
    have never run (or ran outside the window) are treated as unconfirmed.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        total_rows = ctx.sql.query(_SQL_TOTAL)
        audited_rows = ctx.sql.query(_SQL_AUDITED)

        total = int((total_rows[0].get("total_jobs") or 0) if total_rows else 0)
        audited = int((audited_rows[0].get("jobs_with_runs") or 0) if audited_rows else 0)
        # Clamp: jobs_with_runs might exceed total_jobs if deletions race.
        audited = min(audited, total)

        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{audited} of {total} active jobs have run history in "
                    f"system.lakeflow.job_run_timeline (last {_WINDOW_DAYS} days)"
                ),
                detail=f"{_SQL_TOTAL}; {_SQL_AUDITED}",
                rows=[{"total_jobs": total, "jobs_with_runs": audited}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total_jobs"]
        audited = row["jobs_with_runs"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No active jobs found in system.lakeflow.jobs to evaluate audit coverage."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = audited / total
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
            confidence=Confidence.HIGH,
            score=round(ratio, 4),
            rationale=(
                f"{audited} of {total} active jobs ({ratio:.0%}) have execution records "
                f"in system.lakeflow.job_run_timeline over the last {_WINDOW_DAYS} days; "
                f"threshold for 'met' is {_MET_THRESHOLD:.0%}. "
                "Jobs with no run history in the window may be inactive, or their "
                "executions may not be flowing through the platform audit trail."
            ),
            sources=evidence,
        )
