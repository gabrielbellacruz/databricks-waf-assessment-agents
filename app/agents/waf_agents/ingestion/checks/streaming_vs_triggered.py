"""Streaming vs triggered balance check (LLM-judged).

Answers:
  ING-CO-02  Balance always-on streaming against triggered ingestion

Always-on (continuous) jobs keep a cluster running 24/7. Many ingestion
workloads tolerate seconds-to-minutes latency and can use a periodic or
file-arrival trigger instead, which avoids the continuous-cluster cost.
This check counts continuous vs triggered jobs from ``system.lakeflow.jobs``
and lets the LLM judge weigh whether the mix is cost-appropriate.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = (
    "SELECT COUNT(*) AS total_jobs,\n"
    "       SUM(CASE WHEN trigger.continuous IS NOT NULL\n"
    "               THEN 1 ELSE 0 END) AS continuous_jobs,\n"
    "       SUM(CASE WHEN trigger.periodic IS NOT NULL\n"
    "                  OR trigger.file_arrival IS NOT NULL\n"
    "               THEN 1 ELSE 0 END) AS triggered_jobs\n"
    "FROM system.lakeflow.jobs\n"
    "WHERE delete_time IS NULL"
)

_REF = "https://docs.databricks.com/en/structured-streaming/triggers.html"


@register(layer="ingestion", question_ids=["ING-CO-02"])
class StreamingVsTriggeredCheck(Check):
    """Count always-on vs triggered jobs to surface potential streaming overuse."""

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        if not rows:
            return [
                Evidence(
                    kind="sql",
                    summary=(
                        "No rows returned from system.lakeflow.jobs; "
                        "cannot assess trigger mix."
                    ),
                    detail=_SQL,
                    rows=[],
                    ref=_REF,
                )
            ]

        row = rows[0]
        total = int(row.get("total_jobs") or 0)
        continuous = int(row.get("continuous_jobs") or 0)
        triggered = int(row.get("triggered_jobs") or 0)

        summary = (
            f"{continuous} of {total} active jobs are always-on (continuous); "
            f"{triggered} use a periodic or file-arrival trigger."
        )
        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=[
                    {
                        "total_jobs": total,
                        "continuous_jobs": continuous,
                        "triggered_jobs": triggered,
                    }
                ],
                ref=_REF,
            )
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
