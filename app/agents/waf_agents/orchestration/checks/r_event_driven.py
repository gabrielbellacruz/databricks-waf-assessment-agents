"""Event-driven trigger check for orchestration (LLM-judged).

Answers:
  ORC-R-05  React to platform events in workflows

Reacting to platform events (file arrivals, table updates, pipeline completions)
lets workflows start as soon as data is ready rather than polling on a fixed
schedule or running manually.  ``system.lakeflow.jobs`` exposes the trigger
type for each job:

  - ``trigger.file_arrival IS NOT NULL`` → file-arrival (event-driven)
  - ``trigger.continuous IS NOT NULL``   → continuous (always-on streaming mode)
  - ``trigger.schedule IS NOT NULL``     → time-based schedule
  - All triggers NULL (manual)          → manual / API-triggered only

The LLM judge weighs the distribution of trigger types.  Broader event
reactivity (webhooks, DLT event propagation, conditional task chains) is
not observable in system tables; a note records this gap.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT COUNT(*) AS total_jobs,
       SUM(CASE WHEN trigger.file_arrival IS NOT NULL THEN 1 ELSE 0 END) AS file_arrival_jobs,
       SUM(CASE WHEN trigger.schedule IS NOT NULL THEN 1 ELSE 0 END) AS scheduled_jobs,
       SUM(CASE WHEN trigger.continuous IS NOT NULL THEN 1 ELSE 0 END) AS continuous_jobs
FROM system.lakeflow.jobs
WHERE delete_time IS NULL\
"""

_NOTE = (
    "The system.lakeflow.jobs trigger column captures file-arrival, schedule, and "
    "continuous modes.  Broader platform-event reactivity — webhooks, DLT pipeline "
    "completion triggers, conditional task dependencies that react to upstream job "
    "outcomes — is not exposed in system tables and requires manual review of job "
    "configuration and architecture."
)

_REF = "https://docs.databricks.com/en/jobs/triggers.html"


@register(layer="orchestration", question_ids=["ORC-R-05"])
class OrcEventDrivenCheck(Check):
    """Assess platform-event reactivity via trigger types in system.lakeflow.jobs.

    Evidence shows how many jobs use file-arrival, continuous, scheduled, or
    manual triggers.  A note records that broader event reactivity (webhooks,
    DLT event chains) is not visible in system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {}
        total = int(row.get("total_jobs") or 0)
        file_arrival = int(row.get("file_arrival_jobs") or 0)
        scheduled = int(row.get("scheduled_jobs") or 0)
        continuous = int(row.get("continuous_jobs") or 0)

        if total > 0:
            manual = total - file_arrival - scheduled - continuous
            summary = (
                f"{total} active jobs: {file_arrival} file-arrival (event-driven), "
                f"{continuous} continuous, {scheduled} scheduled, {manual} manual"
            )
        else:
            summary = "No active workflow jobs found in system.lakeflow.jobs"

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[{
                "total_jobs": total,
                "file_arrival_jobs": file_arrival,
                "scheduled_jobs": scheduled,
                "continuous_jobs": continuous,
            }],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
