"""Masking and row-filter application check (LLM-judged).

Answers:
  PRO-DG-04  Apply masking/row filters within processing

Signal: query-history statements that reference Unity Catalog row-filter
and column-mask DDL (``SET ROW FILTER``, ``SET MASK``) over the last 90 days.
These are the platform mechanisms for enforcing data-access policies within
transformation pipelines.  A companion note records that the full row-filter
and column-mask policy inventory is not enumerable by the agent's service
principal via system tables, so the statement-count is only a partial proxy.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  SUM(CASE WHEN statement_text ILIKE '%SET ROW FILTER%'
           OR statement_text ILIKE '%SET MASK%'
           OR statement_text ILIKE '%column_mask%'
           OR statement_text ILIKE '%row_filter%'
      THEN 1 ELSE 0 END) AS masking_stmts,
  SUM(CASE WHEN statement_text ILIKE '%DROP ROW FILTER%'
           OR statement_text ILIKE '%DROP MASK%'
      THEN 1 ELSE 0 END) AS drop_masking_stmts,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 90 DAYS\
"""

_NOTE = (
    "The full row-filter and column-mask policy inventory applied to tables "
    "is not enumerable by the agent's service principal via system tables; "
    "query-history DDL statement counts are only a partial proxy — "
    "policies set before the 90-day window and mask functions applied at "
    "table creation will not appear.  Manual confirmation needed."
)

_REF = "https://docs.databricks.com/en/data-governance/unity-catalog/row-and-column-filters.html"


@register(layer="processing", question_ids=["PRO-DG-04"])
class ProcessingMaskingFiltersCheck(Check):
    """Assess masking and row-filter application within processing pipelines.

    Scans ``system.query.history`` (last 90 days) for DDL statements that
    apply (``SET ROW FILTER``, ``SET MASK``) or remove (``DROP ROW FILTER``,
    ``DROP MASK``) Unity Catalog row filters and column masks.  A note records
    that the policy inventory is not fully observable and the LLM judge weighs
    the signal against its stated limitations.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            masking_stmts = int(row.get("masking_stmts") or 0)
            drop_masking_stmts = int(row.get("drop_masking_stmts") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
            summary = (
                f"{masking_stmts} masking/row-filter DDL statement(s) found "
                f"({drop_masking_stmts} drop), out of {total_stmts} total "
                f"statements in the last 90 days"
            )
            sql_evidence = Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=[
                    {
                        "masking_stmts": masking_stmts,
                        "drop_masking_stmts": drop_masking_stmts,
                        "total_stmts": total_stmts,
                    }
                ],
                ref=_REF,
            )
        else:
            sql_evidence = Evidence(
                kind="sql",
                summary="No query-history rows returned — cannot assess masking/row-filter usage",
                detail=_SQL,
                rows=[],
                ref=_REF,
            )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
