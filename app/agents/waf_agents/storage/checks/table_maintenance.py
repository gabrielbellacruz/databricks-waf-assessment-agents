"""Table maintenance automation check (LLM-judged).

Answers:
  STO-OE-01  Automate table maintenance (OPTIMIZE, VACUUM)

Signal: count of OPTIMIZE and VACUUM statements in system.query.history
over the last 30 days. A high and recurring count is a strong proxy for
scheduled/automated maintenance. Zero commands may mean Predictive
Optimization (PO) handles maintenance silently — or it is simply not
being done. The LLM judge weighs both interpretations.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  SUM(CASE WHEN statement_text ILIKE '%OPTIMIZE%' THEN 1 ELSE 0 END) AS optimize_count,
  SUM(CASE WHEN statement_text ILIKE '%VACUUM%' THEN 1 ELSE 0 END) AS vacuum_count,
  COUNT(*) AS total
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS
LIMIT 1\
"""

_NOTE = (
    "If no OPTIMIZE or VACUUM commands appear in query history, there are two "
    "possible explanations: (1) Predictive Optimization (PO) is enabled and "
    "handles maintenance automatically — PO runs are not visible in "
    "system.query.history; or (2) table maintenance is simply not being "
    "performed. Manual confirmation is required to distinguish these cases."
)

_REF = "https://docs.databricks.com/en/delta/optimize.html"


@register(layer="storage", question_ids=["STO-OE-01"])
class TableMaintenanceCheck(Check):
    """Count OPTIMIZE/VACUUM statements in query history as a maintenance proxy.

    A pattern of recurring OPTIMIZE and VACUUM statements over 30 days
    suggests scheduled automation. Zero occurrences could mean Predictive
    Optimization (invisible in query.history) or an absence of maintenance.
    A note evidence records both interpretations for the LLM judge.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            optimize_count = int(rows[0].get("optimize_count") or 0)
            vacuum_count = int(rows[0].get("vacuum_count") or 0)
            total = int(rows[0].get("total") or 0)
        else:
            optimize_count = 0
            vacuum_count = 0
            total = 0

        if total > 0:
            summary = (
                f"OPTIMIZE: {optimize_count} statements, VACUUM: {vacuum_count} statements "
                f"in system.query.history over the last 30 days "
                f"(out of {total} total statements scanned)"
            )
        else:
            summary = (
                "No statements found in system.query.history for the last 30 days"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[{
                "optimize_count": optimize_count,
                "vacuum_count": vacuum_count,
                "total": total,
            }],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
