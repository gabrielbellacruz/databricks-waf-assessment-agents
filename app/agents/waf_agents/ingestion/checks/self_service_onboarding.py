"""Self-service source onboarding check (LLM-judged).

Answers:
  ING-IU-05  Offer a self-service path to onboard new sources

Whether a self-service onboarding path exists (templated request/configure/deploy
flow, Lakeflow Connect UI, internal platform) is an organisational capability not
derivable from system tables.  The check surfaces the count of managed ingestion
pipelines and active jobs as weak, indirect context — a self-service platform tends
to produce many uniform pipelines — and delegates the verdict to the LLM judge,
which is expected to lean toward ``unknown`` given the indirect evidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_PIPELINES = "SELECT COUNT(*) AS pipelines FROM system.lakeflow.pipelines"

_SQL_JOBS = (
    "SELECT COUNT(*) AS jobs FROM system.lakeflow.jobs WHERE delete_time IS NULL"
)

_NOTE_SUMMARY = (
    "Whether a *self-service onboarding path* exists (templated request/configure/"
    "deploy flow, Lakeflow Connect UI, internal platform) is an organizational "
    "capability not derivable from system tables. Pipeline/job volume is only weak, "
    "indirect context. Manual confirmation needed."
)

_REF = "https://docs.databricks.com/en/ingestion/lakeflow-connect/index.html"


@register(layer="ingestion", question_ids=["ING-IU-05"])
class SelfServiceOnboardingCheck(Check):
    """LLM-judged check for ING-IU-05: self-service source onboarding.

    Evidence collected:
      1. Count of managed ingestion pipelines and active jobs from system tables
         (kind ``sql``).  High counts are only a weak proxy for a self-service
         platform; the judge is expected to lean toward ``unknown``.
      2. Caveat note explaining that self-service capability is organisational and
         not directly observable from platform data (kind ``note``).
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        pipeline_rows = ctx.sql.query(_SQL_PIPELINES)
        job_rows = ctx.sql.query(_SQL_JOBS)
        pipelines = int((pipeline_rows[0].get("pipelines") or 0) if pipeline_rows else 0)
        jobs = int((job_rows[0].get("jobs") or 0) if job_rows else 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{pipelines} managed ingestion pipeline(s) and "
                    f"{jobs} active job(s) found in system tables"
                ),
                detail=f"{_SQL_PIPELINES}; {_SQL_JOBS}",
                rows=[{"pipelines": pipelines, "jobs": jobs}],
                ref=_REF,
            ),
            Evidence(
                kind="note",
                summary=_NOTE_SUMMARY,
                rows=[],
                ref=_REF,
            ),
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
