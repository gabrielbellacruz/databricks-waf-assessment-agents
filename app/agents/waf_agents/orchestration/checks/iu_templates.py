"""Reusable workflow templates check (LLM-judged).

Answers:
  ORC-IU-01  Use standard, reusable workflow templates

Whether a team standardises on shared, blessed workflow templates (DAB
bundles, internal platform components, shared job libraries) is an
organisational practice with no direct platform signal.  The closest
observable proxies are naming and tagging regularity across active jobs:

  * A low ratio of distinct first-word name prefixes to total jobs suggests
    many jobs share a common naming convention — a weak indicator of
    templated rather than ad-hoc creation.
  * High tag coverage suggests systematic metadata practices, which
    often accompany template-driven deployment.

Evidence is gathered from ``system.lakeflow.jobs`` via ``ctx.sql``.  A
second Evidence entry records the inherent limit of this proxy signal.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = (
    "SELECT COUNT(*) AS total_jobs, "
    "COUNT(DISTINCT split(name, ' ')[0]) AS distinct_name_prefixes, "
    "SUM(CASE WHEN size(tags) > 0 THEN 1 ELSE 0 END) AS tagged_jobs "
    "FROM system.lakeflow.jobs "
    "WHERE delete_time IS NULL"
)

_NOTE_SUMMARY = (
    "Whether teams use *standard, reusable workflow templates* (DAB bundles, "
    "shared libraries, internal deployment platforms) is an organizational "
    "capability; job-name prefix regularity and tag coverage are only weak "
    "indirect proxies visible in system tables. Manual confirmation needed."
)

_REF = "https://docs.databricks.com/en/dev-tools/bundles/index.html"


@register(layer="orchestration", question_ids=["ORC-IU-01"])
class WorkflowTemplatesCheck(Check):
    """LLM-judged check for ORC-IU-01: standard, reusable workflow templates.

    Evidence collected:
      1. Job naming regularity and tag coverage from system.lakeflow.jobs
         (kind ``sql``).
      2. Caveat note on the limits of platform-observable signals (kind ``note``).
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {}
        total = int(row.get("total_jobs") or 0)
        tagged = int(row.get("tagged_jobs") or 0)
        raw_prefixes = row.get("distinct_name_prefixes")
        distinct_prefixes = int(raw_prefixes) if raw_prefixes is not None else None

        data: dict = {"total_jobs": total, "tagged_jobs": tagged}
        if distinct_prefixes is not None:
            prefix_ratio = round(distinct_prefixes / total, 2) if total > 0 else None
            data["distinct_name_prefixes"] = distinct_prefixes
            if prefix_ratio is not None:
                data["prefix_ratio"] = prefix_ratio
            summary = (
                f"{total} active jobs: {distinct_prefixes} distinct name-prefixes "
                f"(ratio {prefix_ratio}), {tagged} tagged"
            )
        else:
            summary = f"{total} active jobs; {tagged} tagged"

        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=[data],
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
