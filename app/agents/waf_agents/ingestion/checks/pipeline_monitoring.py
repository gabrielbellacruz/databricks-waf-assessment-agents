"""Pipeline monitoring check (LLM-judged).

Answers:
  ING-OE-04  Monitor ingestion pipelines and alert on failures

There is no system-table column that directly records whether email or webhook
alerts are configured on a job. The closest observable proxy is the *observed
failure rate* from ``system.lakeflow.job_run_timeline``: a workspace where
monitoring is absent or broken will tend to accumulate unnoticed failures. The
LLM judge weighs that failure-rate signal together with a note explaining the
gap, and returns a verdict a reviewer can confirm or override.
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

_ALERT_NOTE = (
    "Alert/notification *configuration* (email/webhook on failure) is not exposed in system "
    "tables and the agent's service principal cannot enumerate other teams' job settings, so "
    "this check assesses observed failure volume as a proxy for monitoring health; whether "
    "alerts are wired requires manual confirmation."
)

_ALERT_REF = "https://docs.databricks.com/en/jobs/job-notifications.html"


@register(layer="ingestion", question_ids=["ING-OE-04"])
class PipelineMonitoringCheck(Check):
    """Assess pipeline-monitoring health via recent job-run failure rate.

    Evidence is gathered from ``system.lakeflow.job_run_timeline`` (last 30
    days). A second note evidence records that alert *configuration* is not
    visible to the agent and must be confirmed manually. The LLM judge weighs
    both pieces and produces a verdict capped at medium confidence.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            total = int(rows[0].get("total_runs") or 0)
            failed = int(rows[0].get("failed_runs") or 0)
        else:
            total = 0
            failed = 0

        if total > 0:
            failure_pct = round(100.0 * failed / total, 1)
            summary = (
                f"{failed} of {total} job runs failed/errored/timed-out "
                f"in the last 30 days ({failure_pct}%)"
            )
        else:
            failure_pct = 0.0
            summary = "No job runs found in system.lakeflow.job_run_timeline for the last 30 days"

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[{"total_runs": total, "failed_runs": failed, "failure_pct": failure_pct}],
            ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_ALERT_NOTE,
            rows=[],
            ref=_ALERT_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
