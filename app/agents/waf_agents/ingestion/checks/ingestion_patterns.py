"""Ingestion-pattern characterisation check (LLM-judged).

Answers:
  ING-PE-01  Understand your ingestion patterns and access needs

There is no single number for "the team deliberately characterised each source's
volume, velocity, and freshness requirements."  The closest observable proxy is the
distribution of trigger modes across active jobs: continuous, periodic, file-arrival,
or untriggered.  A workspace that uses only one trigger mode may not have thought about
whether that mode is the right fit for every source; a healthy mix of modes suggests
deliberate design choices per source.

The trigger-mode distribution is gathered from ``system.lakeflow.jobs`` via
``ctx.sql`` (no artifact API calls required).  A second Evidence entry explicitly
records the inherent limit of this signal — whether the team has documented their
source characterisation is an organisational practice that is not directly observable
from platform data.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = (
    "SELECT COUNT(*) AS total_jobs, "
    "SUM(CASE WHEN trigger.continuous IS NOT NULL THEN 1 ELSE 0 END) AS continuous, "
    "SUM(CASE WHEN trigger.periodic IS NOT NULL THEN 1 ELSE 0 END) AS periodic, "
    "SUM(CASE WHEN trigger.file_arrival IS NOT NULL THEN 1 ELSE 0 END) AS file_arrival, "
    "SUM(CASE WHEN trigger IS NULL THEN 1 ELSE 0 END) AS untriggered "
    "FROM system.lakeflow.jobs WHERE delete_time IS NULL"
)

_NOTE = (
    "Whether the team has *deliberately characterized* each source's volume/velocity/"
    "freshness needs is an organizational practice not fully visible in platform data; "
    "the trigger-mode distribution is an indirect signal only."
)

_REF = (
    "https://docs.databricks.com/en/lakehouse-architecture/"
    "performance-efficiency/best-practices.html"
)


@register(layer="ingestion", question_ids=["ING-PE-01"])
class IngestionPatternsCheck(Check):
    """LLM-judged check for ING-PE-01: ingestion-pattern characterisation.

    Evidence collected:
      1. Trigger-mode distribution from ``system.lakeflow.jobs`` (kind ``sql``).
      2. Caveat note explaining the limits of platform-observable signals (kind ``note``).
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {}
        total = int(row.get("total_jobs") or 0)
        continuous = int(row.get("continuous") or 0)
        periodic = int(row.get("periodic") or 0)
        file_arrival = int(row.get("file_arrival") or 0)
        untriggered = int(row.get("untriggered") or 0)
        distribution = {
            "total_jobs": total,
            "continuous": continuous,
            "periodic": periodic,
            "file_arrival": file_arrival,
            "untriggered": untriggered,
        }
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{total} active jobs: {continuous} continuous, {periodic} periodic, "
                    f"{file_arrival} file-arrival, {untriggered} untriggered"
                ),
                detail=_SQL,
                rows=[distribution],
                ref=_REF,
            ),
            Evidence(
                kind="note",
                summary=_NOTE,
                rows=[],
            ),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
