"""Self-service scheduling check (LLM-judged).

Answers:
  ORC-IU-02  Provide self-service scheduling for teams

Whether a self-service scheduling path exists (a portal, API, or platform that
lets teams create and own their own jobs without raising a ticket) is an
organisational capability not directly observable from system tables.

Two weak proxy signals are gathered via ``ctx.sql``:
  1. The count of jobs with a schedule set and the number of distinct
     ``run_as`` identities across all active jobs
     (``system.lakeflow.jobs``).  Many distinct owners with their own
     schedules is a proxy for teams self-managing their workflows.
  2. The count of active DLT pipelines (``system.lakeflow.pipelines``) as an
     additional signal that teams are autonomously managing data pipelines.

A second Evidence entry records the inherent limit of these proxies.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_JOBS = (
    "SELECT COUNT(*) AS total_jobs, "
    "SUM(CASE WHEN schedule IS NOT NULL THEN 1 ELSE 0 END) AS scheduled_jobs, "
    "COUNT(DISTINCT run_as) AS distinct_owners "
    "FROM system.lakeflow.jobs "
    "WHERE delete_time IS NULL"
)

_SQL_PIPELINES = (
    "SELECT COUNT(*) AS active_pipelines "
    "FROM system.lakeflow.pipelines"
)

_NOTE_SUMMARY = (
    "Whether a *self-service scheduling path* exists (portal, API, or internal "
    "platform that lets teams own their own job schedules) is an organizational "
    "capability not derivable from system tables. Schedule count and distinct "
    "owner count are only weak, indirect proxies. Manual confirmation needed."
)

_REF = "https://docs.databricks.com/en/workflows/jobs/schedule-jobs-ui.html"


@register(layer="orchestration", question_ids=["ORC-IU-02"])
class SelfServiceSchedulingCheck(Check):
    """LLM-judged check for ORC-IU-02: self-service scheduling for teams.

    Evidence collected:
      1. Scheduled-job count and distinct-owner count from system.lakeflow.jobs
         (kind ``sql``).
      2. Active pipeline count from system.lakeflow.pipelines (kind ``sql``).
      3. Caveat note that self-service capability is organisational (kind ``note``).
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        # --- evidence 1: scheduled jobs + distinct owners ---
        job_rows = ctx.sql.query(_SQL_JOBS)
        job_row = job_rows[0] if job_rows else {}
        total_jobs = int(job_row.get("total_jobs") or 0)
        scheduled_jobs = int(job_row.get("scheduled_jobs") or 0)
        distinct_owners = int(job_row.get("distinct_owners") or 0)
        ev_jobs = Evidence(
            kind="sql",
            summary=(
                f"{scheduled_jobs} of {total_jobs} active jobs have a schedule; "
                f"{distinct_owners} distinct run_as owner(s)"
            ),
            detail=_SQL_JOBS,
            rows=[{
                "total_jobs": total_jobs,
                "scheduled_jobs": scheduled_jobs,
                "distinct_owners": distinct_owners,
            }],
            ref=_REF,
        )

        # --- evidence 2: active DLT pipelines ---
        pl_rows = ctx.sql.query(_SQL_PIPELINES)
        pl_row = pl_rows[0] if pl_rows else {}
        active_pipelines = int(pl_row.get("active_pipelines") or 0)
        ev_pipelines = Evidence(
            kind="sql",
            summary=f"{active_pipelines} active DLT pipeline(s) registered",
            detail=_SQL_PIPELINES,
            rows=[{"active_pipelines": active_pipelines}],
            ref=_REF,
        )

        ev_note = Evidence(
            kind="note",
            summary=_NOTE_SUMMARY,
            rows=[],
            ref=_REF,
        )

        return [ev_jobs, ev_pipelines, ev_note]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
