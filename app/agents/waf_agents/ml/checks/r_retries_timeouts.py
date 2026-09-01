"""Retries and timeouts for training jobs (LLM-judged).

Answers:
  ML-R-02  Configure retries and timeouts for training jobs

Whether training jobs have automatic retries and per-task timeouts
*configured* is a Jobs-API setting not exposed in system tables and not
enumerable by this agent's service principal. The observable proxy is
TIMED_OUT / repeated runs in ``system.lakeflow.job_run_timeline``:
TIMED_OUT presence indicates timeouts ARE configured; a high failure
rate with no TIMED_OUT runs is a risk signal. The LLM judge weighs both
pieces and produces a verdict a reviewer can confirm or override.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  COUNT(*) AS total_runs,
  SUM(CASE WHEN result_state = 'TIMED_OUT' THEN 1 ELSE 0 END) AS timed_out_runs,
  SUM(CASE WHEN result_state IN ('FAILED', 'ERROR') THEN 1 ELSE 0 END) AS failed_runs,
  SUM(CASE WHEN result_state = 'SUCCEEDED' THEN 1 ELSE 0 END) AS succeeded_runs
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Whether training jobs have automatic retries and task-level timeouts *configured* is "
    "a Jobs-API setting not exposed in system tables and not accessible via the agent's "
    "service principal. Observed TIMED_OUT and failure counts are only an indirect proxy — "
    "Manual confirmation of job retry/timeout settings is needed."
)

_REF = "https://docs.databricks.com/en/jobs/settings.html"


@register(layer="ml", question_ids=["ML-R-02"])
class MlRetriesTimeoutsCheck(Check):
    """Assess training-job retry/timeout configuration via recent run outcomes.

    Evidence is gathered from system.lakeflow.job_run_timeline (last 30
    days): total runs, TIMED_OUT count, FAILED/ERROR count, SUCCEEDED count.
    TIMED_OUT presence is a positive proxy for timeout configuration; a high
    failure rate with no TIMED_OUT runs signals that timeouts may not be set.
    A note evidence records the observability limit. The LLM judge weighs both.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            total = int(row.get("total_runs") or 0)
            timed_out = int(row.get("timed_out_runs") or 0)
            failed = int(row.get("failed_runs") or 0)
            succeeded = int(row.get("succeeded_runs") or 0)
        else:
            total = timed_out = failed = succeeded = 0

        if total > 0:
            fail_pct = round(100.0 * failed / total, 1)
            sql_summary = (
                f"{total} job runs in the last 30 days: "
                f"{succeeded} SUCCEEDED, {failed} FAILED/ERROR ({fail_pct}%), "
                f"{timed_out} TIMED_OUT"
            )
        else:
            sql_summary = (
                "No job runs found in system.lakeflow.job_run_timeline for the last 30 days"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=sql_summary,
            detail=_SQL,
            rows=[
                {
                    "total_runs": total,
                    "timed_out_runs": timed_out,
                    "failed_runs": failed,
                    "succeeded_runs": succeeded,
                }
            ],
            ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
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
