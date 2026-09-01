"""Join optimisation check (LLM-judged).

Answers:
  PRO-PE-02  Optimize joins in transformations

Poorly-tuned joins (missing broadcast hints on small tables, data skew causing
shuffle amplification, suboptimal join order) are a common source of
transformation slowness.  The closest observable proxy is the use of explicit
join-strategy hints — BROADCAST / BROADCASTJOIN, SKEW HINT, MERGE hints — in
``system.query.history``.  These hint patterns signal that the team is actively
tuning joins; their absence is a weak risk signal.  The LLM judge weighs the
evidence and returns a verdict a reviewer can confirm or override.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  SUM(CASE WHEN statement_text ILIKE '%BROADCAST%' THEN 1 ELSE 0 END)
      AS broadcast_hints,
  SUM(CASE WHEN statement_text ILIKE '%SKEW%' THEN 1 ELSE 0 END)
      AS skew_hints,
  SUM(CASE WHEN statement_text ILIKE '%MERGE%JOIN%'
            OR statement_text ILIKE '%SHUFFLE%HASH%'
       THEN 1 ELSE 0 END)
      AS merge_shuffle_hints,
  SUM(CASE WHEN statement_text ILIKE '% JOIN %' THEN 1 ELSE 0 END)
      AS join_stmts,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_JOIN_NOTE = (
    "Hint presence in query text is only a weak proxy for join optimisation.  "
    "The absence of explicit hints does not mean joins are unoptimised — the "
    "optimizer may choose a broadcast plan automatically for small tables.  "
    "Spark UI / Query Profile analysis is needed to identify actual join "
    "bottlenecks and skew; that data is not available in system tables."
)

_JOIN_REF = "https://docs.databricks.com/en/optimizations/join-optimizations.html"


@register(layer="processing", question_ids=["PRO-PE-02"])
class JoinOptimizationCheck(Check):
    """Assess join-optimisation practice via explicit hint patterns in query history.

    Evidence is gathered from ``system.query.history`` (last 30 days).  Counts
    of BROADCAST, SKEW, MERGE/SHUFFLE HASH hints and overall JOIN statement
    frequency are reported.  A note evidence records that hint absence doesn't
    confirm problems and that manual or Spark UI review is required.  The LLM judge
    weighs both pieces and produces a verdict.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            broadcast_hints = int(row.get("broadcast_hints") or 0)
            skew_hints = int(row.get("skew_hints") or 0)
            merge_shuffle_hints = int(row.get("merge_shuffle_hints") or 0)
            join_stmts = int(row.get("join_stmts") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
        else:
            broadcast_hints = 0
            skew_hints = 0
            merge_shuffle_hints = 0
            join_stmts = 0
            total_stmts = 0

        total_hints = broadcast_hints + skew_hints + merge_shuffle_hints

        if total_stmts == 0:
            summary = (
                "No query-history rows found for the last 30 days"
                " — cannot assess join optimisation hints"
            )
        else:
            summary = (
                f"Join-optimisation hints (last 30 days): "
                f"BROADCAST={broadcast_hints}, SKEW={skew_hints}, "
                f"MERGE/SHUFFLE_HASH={merge_shuffle_hints} (total hints={total_hints}); "
                f"JOIN statements={join_stmts}; total statements={total_stmts}"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[
                {
                    "broadcast_hints": broadcast_hints,
                    "skew_hints": skew_hints,
                    "merge_shuffle_hints": merge_shuffle_hints,
                    "join_stmts": join_stmts,
                    "total_stmts": total_stmts,
                }
            ],
            ref=_JOIN_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_JOIN_NOTE,
            rows=[],
            ref=_JOIN_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
