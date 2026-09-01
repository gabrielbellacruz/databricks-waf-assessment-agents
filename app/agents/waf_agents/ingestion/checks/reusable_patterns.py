"""Reusable ingestion patterns check (LLM-judged).

Answers:
  ING-IU-02  Use standard, reusable ingestion patterns

Whether a team uses blessed, reusable ingestion building blocks — DAB templates,
shared libraries, or job templates — is an organisational practice with no direct
platform signal.  The closest observable proxy is naming and tagging regularity
across active jobs: a low ratio of distinct name-prefixes to total jobs and
consistent tag coverage suggest templated rather than one-off jobs.

Evidence is gathered from ``system.lakeflow.jobs`` via ``ctx.sql`` (no artifact
API calls required).  A second Evidence entry records the inherent limit of this
proxy signal so a reviewer can calibrate their confidence.
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

_NOTE = (
    "Whether teams share *blessed, reusable* ingestion patterns (templates, "
    "shared libraries, DAB templates) is an organizational practice; "
    "job-name/tag regularity is only a weak indirect proxy visible in system "
    "tables. Manual confirmation needed."
)

_REF = "https://docs.databricks.com/en/dev-tools/bundles/index.html"


@register(layer="ingestion", question_ids=["ING-IU-02"])
class ReusablePatternsCheck(Check):
    """LLM-judged check for ING-IU-02: reusable ingestion patterns.

    Evidence collected:
      1. Job naming/tagging regularity from ``system.lakeflow.jobs`` (kind ``sql``).
      2. Caveat note on the limits of platform-observable signals (kind ``note``).
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {}
        total = int(row.get("total_jobs") or 0)
        tagged = int(row.get("tagged_jobs") or 0)
        raw_prefixes = row.get("distinct_name_prefixes")
        distinct_prefixes = int(raw_prefixes) if raw_prefixes is not None else None

        data: dict[str, float | None] = {"total_jobs": total, "tagged_jobs": tagged}
        if distinct_prefixes is not None:
            prefix_ratio = round(distinct_prefixes / total, 2) if total > 0 else None
            data["distinct_name_prefixes"] = distinct_prefixes
            if prefix_ratio is not None:
                data["prefix_ratio"] = prefix_ratio
            summary = (
                f"{total} active jobs: {distinct_prefixes} distinct name-prefixes"
                f" (ratio {prefix_ratio}), {tagged} tagged"
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
                summary=_NOTE,
                rows=[],
            ),
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
