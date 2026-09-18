"""Right-size compute check for the processing layer (LLM-judged).

Answers:
  PRO-CO-02  Right-size compute for transformation jobs

No single metric proves every job is right-sized. The best proxies are:
  - The rate of failed/timed-out job runs over the last 30 days; OOM and
    timeout failures often indicate under-sizing.
  - Average and maximum task durations from system.query.history over the
    same window.
The LLM judge weighs these signals against WAF right-sizing guidance.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_RUNS_SQL = """\
SELECT
  COUNT(*) AS total_runs,
  SUM(CASE WHEN result_state IN ('FAILED', 'TIMED_OUT', 'ERROR')
           THEN 1 ELSE 0 END) AS failed_runs,
  SUM(CASE WHEN result_state = 'SUCCEEDED' THEN 1 ELSE 0 END) AS success_runs
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_QUERY_SQL = """\
SELECT
  COUNT(*) AS total_queries,
  AVG(total_task_duration_ms) AS avg_task_ms,
  MAX(total_task_duration_ms) AS max_task_ms
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS
LIMIT 1\
"""

_REF = "https://docs.databricks.com/en/compute/cluster-config-best-practices.html"

_NOTE = (
    "Right-sizing is a judgement call: failure rates and task durations are proxies, "
    "not proof. OOM failures (FAILED/TIMEDOUT runs) and very long task durations suggest "
    "under-sizing; very low DBU utilisation (not captured here) suggests over-sizing. "
    "system.lakeflow.job_run_timeline covers the last 30 days; "
    "system.query.history is polled with a 30-day window and may be incomplete on "
    "high-volume workspaces."
)


@register(layer="processing", question_ids=["PRO-CO-02"])
class ProcessingRightSizeCheck(Check):
    """Collect job-run failure rates and query-duration metrics as right-sizing proxies.

    High failure/timeout rates signal under-sizing. The LLM judge weighs the
    failure rate and duration distribution against WAF right-sizing guidance.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        # Signal 1: job run failure rates from lakeflow system table
        run_rows = ctx.sql.query(_RUNS_SQL)
        if run_rows:
            r = run_rows[0]
            total_runs = int(r.get("total_runs") or 0)
            failed_runs = int(r.get("failed_runs") or 0)
            success_runs = int(r.get("success_runs") or 0)
        else:
            total_runs = failed_runs = success_runs = 0

        fail_pct = round(100.0 * failed_runs / total_runs, 1) if total_runs > 0 else 0.0
        runs_summary = (
            f"{total_runs} job runs in the last 30 days: "
            f"{success_runs} succeeded, {failed_runs} failed/timed-out "
            f"({fail_pct}% failure rate)"
        )
        run_evidence = Evidence(
            kind="sql",
            summary=runs_summary,
            detail=_RUNS_SQL,
            rows=[{
                "total_runs": total_runs,
                "failed_runs": failed_runs,
                "success_runs": success_runs,
                "fail_pct": fail_pct,
            }],
            ref=_REF,
        )

        # Signal 2: query task-duration distribution from query history
        q_rows = ctx.sql.query(_QUERY_SQL)
        if q_rows:
            q = q_rows[0]
            total_queries = int(q.get("total_queries") or 0)
            avg_ms = float(q.get("avg_task_ms") or 0)
            max_ms = float(q.get("max_task_ms") or 0)
        else:
            total_queries = 0
            avg_ms = max_ms = 0.0

        q_summary = (
            f"{total_queries} queries in system.query.history over 30 days; "
            f"avg task duration {avg_ms / 1000:.1f}s, max {max_ms / 1000:.1f}s"
        )
        query_evidence = Evidence(
            kind="sql",
            summary=q_summary,
            detail=_QUERY_SQL,
            rows=[{
                "total_queries": total_queries,
                "avg_task_ms": avg_ms,
                "max_task_ms": max_ms,
            }],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [run_evidence, query_evidence, note_evidence]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
