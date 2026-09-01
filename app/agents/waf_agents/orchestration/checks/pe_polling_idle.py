"""Polling and idle-wait check for orchestration (LLM-judged).

Answers:
  ORC-PE-05  Avoid unnecessary polling and idle waits

Polling loops (``time.sleep`` + status check) and long idle waits in notebook
tasks burn cluster compute without doing useful work.  Databricks Workflows
provides built-in waiting primitives (task dependencies, the ``Wait`` task
type, file-arrival triggers) that avoid manual polling.

Observable proxies:
  1. ``system.lakeflow.job_run_timeline`` — jobs with unusually long run times
     relative to the 30-day average may have idle/polling phases.
  2. ``system.query.history`` — statements that poll ``job_run_timeline``
     itself (users manually querying job status instead of using Workflows
     built-in waiting) are an anti-pattern signal.

Actual polling code (Python ``time.sleep`` loops) in notebooks is not
observable in system tables; a note records this gap.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_DURATION = """\
SELECT COUNT(DISTINCT run_id) AS total_runs,
       AVG(CAST(period_end_time AS DOUBLE) - CAST(period_start_time AS DOUBLE))
           AS avg_run_seconds,
       MAX(CAST(period_end_time AS DOUBLE) - CAST(period_start_time AS DOUBLE))
           AS max_run_seconds
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS
  AND period_end_time IS NOT NULL\
"""

_SQL_POLL_HISTORY = """\
SELECT COUNT(*) AS status_poll_statements
FROM system.query.history
WHERE statement_text ILIKE '%job_run_timeline%'
  AND start_time >= current_timestamp() - INTERVAL 30 DAYS
LIMIT 1\
"""

_NOTE = (
    "Polling patterns implemented as Python time.sleep loops or notebook-level "
    "busy-waits are not observable in system tables.  The job-run duration "
    "statistics and query-history poll count are indirect proxies only.  Manual "
    "review of notebook task code and use of Workflows' built-in dependency "
    "waiting (task dependencies, Wait task type, file-arrival triggers) is "
    "required to assess this practice."
)

_REF = "https://docs.databricks.com/en/jobs/wait.html"


@register(layer="orchestration", question_ids=["ORC-PE-05"])
class OrcPollingIdleCheck(Check):
    """Assess polling/idle-wait risk via run durations and query-history signals.

    Evidence is gathered from:
      - ``system.lakeflow.job_run_timeline`` (avg/max run duration, last 30 days)
      - ``system.query.history``             (manual job-status queries as polling proxy)
    A note records that actual polling code in notebooks is not system-table visible.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        # --- evidence 1: run duration (idle indicator) ---
        dur_rows = ctx.sql.query(_SQL_DURATION)
        dur_row = dur_rows[0] if dur_rows else {}
        total_runs = int(dur_row.get("total_runs") or 0)
        avg_raw = dur_row.get("avg_run_seconds")
        max_raw = dur_row.get("max_run_seconds")
        avg_secs = round(float(avg_raw), 1) if avg_raw is not None else None
        max_secs = round(float(max_raw), 1) if max_raw is not None else None

        if total_runs > 0:
            dur_parts = []
            if avg_secs is not None:
                dur_parts.append(f"avg {avg_secs}s")
            if max_secs is not None:
                dur_parts.append(f"max {max_secs}s")
            dur_str = " (" + ", ".join(dur_parts) + ")" if dur_parts else ""
            dur_summary = (
                f"{total_runs} workflow runs over the last 30 days{dur_str}; "
                "unusually long max durations may indicate polling or idle tasks"
            )
        else:
            dur_summary = "No workflow runs found in job_run_timeline for the last 30 days"

        ev_duration = Evidence(
            kind="sql",
            summary=dur_summary,
            detail=_SQL_DURATION,
            rows=[{
                "total_runs": total_runs,
                "avg_run_seconds": avg_secs,
                "max_run_seconds": max_secs,
            }],
            ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
        )

        # --- evidence 2: manual status polling in query history ---
        poll_rows = ctx.sql.query(_SQL_POLL_HISTORY)
        poll_row = poll_rows[0] if poll_rows else {}
        poll_count = int(poll_row.get("status_poll_statements") or 0)

        ev_poll = Evidence(
            kind="sql",
            summary=(
                f"{poll_count} queries in the last 30 days directly query "
                "system.lakeflow.job_run_timeline (potential manual polling anti-pattern)"
            ),
            detail=_SQL_POLL_HISTORY,
            rows=[{"status_poll_statements": poll_count}],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [ev_duration, ev_poll, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
