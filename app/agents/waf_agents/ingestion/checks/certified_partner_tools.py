"""Certified partner tools check (LLM-judged).

Answers:
  ING-IU-04  Use certified partner tools for ingestion

Signal (weak / indirect): the distribution of ``source_type`` values recorded
in ``system.access.table_lineage`` over the last 90 days. These values reflect
how data entered the lakehouse, but give no indication of whether the originating
tool holds a Databricks Partner Certification. Certification status can only be
confirmed by a Solutions Architect; the check surfaces what it can observe and
defers to the LLM judge, which is expected to lean toward ``unknown`` given the
indirect evidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 90

_SQL = (
    "SELECT source_type, COUNT(*) AS n "
    "FROM system.access.table_lineage "
    f"WHERE event_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS "
    "AND source_type IS NOT NULL "
    "GROUP BY source_type "
    "ORDER BY n DESC"
)

_NOTE_SUMMARY = (
    "Whether ingestion tools are Databricks-certified partners is not derivable "
    "from platform data; this check only surfaces observed source types. "
    "Certification status requires manual confirmation."
)

_PARTNER_REF = "https://www.databricks.com/company/partners/technology"


@register(layer="ingestion", question_ids=["ING-IU-04"])
class CertifiedPartnerToolsCheck(Check):
    """Surfaces the source types observed in table_lineage and asks the LLM to
    judge whether they suggest the use of certified partner tools.

    Evidence is weak and indirect; the judge is expected to return ``unknown``
    unless the source types clearly indicate a Databricks-certified tool.
    Certification cannot be derived from platform data alone."""

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        total = sum(int(r.get("n") or 0) for r in rows)
        source_count = len(rows)
        summary = (
            f"{source_count} distinct source_type(s) observed in table_lineage "
            f"over the last {_WINDOW_DAYS} days ({total} total lineage events)"
        )
        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=rows[:25],
                ref=_PARTNER_REF,
            ),
            Evidence(
                kind="note",
                summary=_NOTE_SUMMARY,
                rows=[],
                ref=_PARTNER_REF,
            ),
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
