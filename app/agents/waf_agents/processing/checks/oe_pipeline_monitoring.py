"""Pipeline run monitoring and data freshness check (LLM-judged).

Answers:
  PRO-OE-03  Monitor pipeline runs and data freshness

Mirrors the ingestion pipeline_monitoring check re-framed for transformation
pipelines. Signal: observed failure rate from system.lakeflow.job_run_timeline
over the last 30 days; a note records that alert configuration and data-freshness
monitoring are not visible via system tables.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT COUNT(*) AS total_runs,
       SUM(CASE WHEN result_state IN ('FAILED','ERROR','TIMED_OUT') THEN 1 ELSE 0 END)
           AS failed_runs
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Alert/notification *configuration* (email/webhook on failure) and data-freshness "
    "SLAs are not exposed in system tables; the agent's service principal cannot enumerate "
    "other teams' job alert settings. This check uses observed failure volume as a proxy "
    "for monitoring health; whether alerts are wired and freshness SLAs are tracked "
    "requires manual confirmation."
)

_ALERT_REF = "https://docs.databricks.com/en/jobs/job-notifications.html"


@register(layer="processing", question_ids=["PRO-OE-03"])
class PipelineMonitoringCheck(Check):
    """Assess monitoring health via recent job-run failure rate.

    Evidence is from system.lakeflow.job_run_timeline (last 30 days). A note
    records that alert configuration and data-freshness monitoring are not
    visible to the agent and must be confirmed manually. The LLM judge
    weighs both pieces.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        total = int(rows[0].get("total_runs") or 0) if rows else 0
        failed = int(rows[0].get("failed_runs") or 0) if rows else 0

        if total > 0:
            failure_pct = round(100.0 * failed / total, 1)
            summary = (
                f"{failed} of {total} job runs failed/errored/timed-out "
                f"in the last 30 days ({failure_pct}%)"
            )
        else:
            failure_pct = 0.0
            summary = (
                "No job runs found in system.lakeflow.job_run_timeline for the last 30 days"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[{"total_runs": total, "failed_runs": failed, "failure_pct": failure_pct}],
            ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
        )
        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_ALERT_REF,
        )
        return [sql_evidence, note_evidence]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
