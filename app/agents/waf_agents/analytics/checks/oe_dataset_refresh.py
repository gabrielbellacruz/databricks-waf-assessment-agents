"""Analytics dataset refresh automation check (LLM-judged).

Answers:
  ANA-OE-03  Automate refresh of analytics datasets

Whether a job specifically refreshes an analytics dataset is not exposed in
system tables. The observable proxy is the trigger-type distribution from
system.lakeflow.job_run_timeline (last 30 days): SCHEDULED, CONTINUOUS, and
FILE_ARRIVAL runs indicate automated execution while MANUAL and ONE_TIME runs
indicate manual triggering. A note records that which jobs serve analytics vs.
other workloads requires manual confirmation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT trigger_type,
       COUNT(*) AS run_count
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS
GROUP BY trigger_type\
"""

_AUTOMATED_TRIGGERS = frozenset(
    {"SCHEDULED", "CONTINUOUS", "FILE_ARRIVAL", "CRON", "PERIODIC"}
)

_NOTE = (
    "Which jobs specifically refresh analytics datasets (vs. ETL, ML, or other workloads) "
    "is not determinable from system tables alone. The trigger_type distribution is used as "
    "a proxy: SCHEDULED/CONTINUOUS/FILE_ARRIVAL runs indicate automated execution; "
    "MANUAL/ONE_TIME runs indicate manual triggering. Manual confirmation of which jobs serve "
    "analytics datasets is recommended."
)

_REF = "https://docs.databricks.com/en/jobs/create-run-jobs.html"


@register(layer="analytics", question_ids=["ANA-OE-03"])
class DatasetRefreshCheck(Check):
    """Assess analytics dataset refresh automation via job trigger-type distribution.

    Evidence is gathered from system.lakeflow.job_run_timeline (last 30 days).
    A note evidence records that identifying analytics-specific jobs requires manual input.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        scheduled = 0
        total = 0
        for row in rows:
            trigger = str(row.get("trigger_type") or "UNKNOWN").upper()
            count = int(row.get("run_count") or 0)
            total += count
            if trigger in _AUTOMATED_TRIGGERS:
                scheduled += count

        if total > 0:
            sched_pct = round(100.0 * scheduled / total, 1)
            summary = (
                f"{scheduled} of {total} job runs in the last 30 days were triggered "
                f"automatically (SCHEDULED/CONTINUOUS/FILE_ARRIVAL) — {sched_pct}%"
            )
        else:
            summary = (
                "No job runs found in system.lakeflow.job_run_timeline for the last 30 days"
            )

        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=rows[:20],
                ref=_REF,
            ),
            Evidence(
                kind="note",
                summary=_NOTE,
                rows=[],
                ref=_REF,
            ),
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
