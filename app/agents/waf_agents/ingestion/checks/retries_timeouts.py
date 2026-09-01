"""Retries and timeouts check (LLM-judged).

Answers:
  ING-R-02  Configure ingestion jobs for automatic retries and timeouts

Whether jobs have automatic retries and task timeouts *configured* is a
Jobs-API setting not exposed in system tables and not enumerable by this
agent's service principal. The observable proxy is TIMED_OUT / repeated runs
in ``system.lakeflow.job_run_timeline``: TIMED_OUT presence indicates timeouts
ARE configured; a high failure rate with no timeouts is a risk signal. The LLM
judge weighs both pieces and returns a verdict a reviewer can confirm or override.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT COUNT(*) AS total_runs,
       SUM(CASE WHEN result_state = 'TIMED_OUT' THEN 1 ELSE 0 END) AS timed_out_runs,
       SUM(CASE WHEN result_state IN ('FAILED','ERROR') THEN 1 ELSE 0 END) AS failed_runs
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_RETRY_NOTE = (
    "Whether jobs have automatic retries and task timeouts *configured* is a Jobs-API setting "
    "not exposed in system tables and not enumerable by this agent's service principal. "
    "Observed TIMED_OUT/failure counts are only an indirect proxy — manual confirmation needed."
)

_RETRY_REF = "https://docs.databricks.com/en/jobs/settings.html"


@register(layer="ingestion", question_ids=["ING-R-02"])
class RetriesTimeoutsCheck(Check):
    """Assess retry/timeout configuration via recent TIMED_OUT and failure counts.

    Evidence is gathered from ``system.lakeflow.job_run_timeline`` (last 30
    days). TIMED_OUT presence is a positive proxy for timeout configuration;
    a high failure rate with no TIMED_OUT runs signals that timeouts may not be
    set. A dominant note evidence records that retry/timeout *configuration* is
    a Jobs-API setting invisible to this agent and requires manual confirmation. The
    LLM judge weighs both pieces and produces a verdict.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            total = int(rows[0].get("total_runs") or 0)
            timed_out = int(rows[0].get("timed_out_runs") or 0)
            failed = int(rows[0].get("failed_runs") or 0)
        else:
            total = 0
            timed_out = 0
            failed = 0

        if total > 0:
            summary = (
                f"{total} job runs in the last 30 days: "
                f"{timed_out} TIMED_OUT, {failed} FAILED/ERROR"
            )
        else:
            summary = "No job runs found in system.lakeflow.job_run_timeline for the last 30 days"

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[{"total_runs": total, "timed_out_runs": timed_out, "failed_runs": failed}],
            ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_RETRY_NOTE,
            rows=[],
            ref=_RETRY_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
