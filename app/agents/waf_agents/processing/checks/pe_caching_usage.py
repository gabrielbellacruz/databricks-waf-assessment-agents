"""Caching usage check (LLM-judged).

Answers:
  PRO-PE-03  Use caching where transformations reuse data

Caching intermediate DataFrames or tables that are accessed multiple times in a
transformation chain avoids redundant recomputation.  The closest observable
proxy is the presence of explicit caching keywords — CACHE TABLE, .cache(),
.persist(), CACHE SELECT — in ``system.query.history``.  Non-zero caching usage
is a positive signal; complete absence when there are many transformation jobs
is a risk signal.  The LLM judge weighs the evidence and returns a verdict the
A reviewer can confirm or override.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  SUM(
    CASE
      WHEN statement_text ILIKE '%CACHE TABLE%'
        OR statement_text ILIKE '%CACHE SELECT%'
        OR statement_text ILIKE '%.cache()%'
        OR statement_text ILIKE '%.persist()%'
        OR statement_text ILIKE '%.persist(%'
      THEN 1 ELSE 0
    END
  ) AS cache_stmts,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_CACHE_NOTE = (
    "Explicit caching keywords in query history are only a weak proxy.  Databricks "
    "Delta caching (disk-level) operates transparently and is not visible in statement "
    "text.  Whether caching is applied at the right points in transformation chains "
    "requires manual or code review to confirm.  Over-caching can consume memory "
    "unnecessarily; under-caching forces recomputation."
)

_CACHE_REF = "https://docs.databricks.com/en/optimizations/disk-cache.html"


@register(layer="processing", question_ids=["PRO-PE-03"])
class CachingUsageCheck(Check):
    """Assess caching practice via explicit caching patterns in query history.

    Evidence is gathered from ``system.query.history`` (last 30 days).  Counts
    of statements containing CACHE TABLE, CACHE SELECT, .cache(), .persist()
    patterns are reported.  A note evidence records that transparent Delta
    disk-cache is not visible here and manual review is required.  The LLM judge
    weighs both pieces and produces a verdict.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            cache_stmts = int(row.get("cache_stmts") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
        else:
            cache_stmts = 0
            total_stmts = 0

        if total_stmts == 0:
            summary = (
                "No query-history rows found for the last 30 days"
                " — cannot assess caching usage"
            )
        else:
            cache_pct = round(100.0 * cache_stmts / total_stmts, 1)
            summary = (
                f"{cache_stmts} of {total_stmts} statements ({cache_pct}%) use explicit caching "
                f"(CACHE TABLE / CACHE SELECT / .cache() / .persist()) in the last 30 days"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[{"cache_stmts": cache_stmts, "total_stmts": total_stmts}],
            ref=_CACHE_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_CACHE_NOTE,
            rows=[],
            ref=_CACHE_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
