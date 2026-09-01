"""Idempotent transformations check (LLM-judged).

Answers:
  PRO-R-02  Make transformations idempotent

True idempotency is a code-level property — the same transformation run twice
must produce the same result.  It cannot be observed directly from system
tables.  The closest proxy is the mix of write patterns in
``system.query.history``: MERGE INTO and REPLACE WHERE are naturally idempotent;
INSERT OVERWRITE replaces a full partition and is repeatable; plain INSERT INTO
without deduplication guards is not idempotent.  A high share of idempotent
write patterns is a positive signal; a heavy reliance on plain INSERT INTO
is a risk signal.  The LLM judge weighs the evidence and returns a verdict
A reviewer can confirm or override.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  SUM(CASE WHEN statement_text ILIKE '%MERGE INTO%' THEN 1 ELSE 0 END)
      AS merge_into_stmts,
  SUM(CASE WHEN statement_text ILIKE '%REPLACE WHERE%' THEN 1 ELSE 0 END)
      AS replace_where_stmts,
  SUM(CASE WHEN statement_text ILIKE '%INSERT OVERWRITE%' THEN 1 ELSE 0 END)
      AS insert_overwrite_stmts,
  SUM(CASE WHEN statement_text ILIKE '%INSERT INTO%' THEN 1 ELSE 0 END)
      AS insert_into_stmts,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_IDEMPOTENCY_NOTE = (
    "True idempotency is a code-level property not directly observable in system tables. "
    "Write-pattern counts (MERGE INTO, REPLACE WHERE, INSERT OVERWRITE vs INSERT INTO) "
    "are only a proxy — whether each transformation is safe to retry without duplicating "
    "data requires manual or code review to confirm."
)

_IDEMPOTENCY_REF = "https://docs.databricks.com/en/delta/merge.html"


@register(layer="processing", question_ids=["PRO-R-02"])
class IdempotentTransformationsCheck(Check):
    """Assess idempotency of transformations via write-pattern mix in query history.

    Evidence is gathered from ``system.query.history`` (last 30 days).  MERGE
    INTO, REPLACE WHERE, and INSERT OVERWRITE are counted as idempotency-safe
    patterns; INSERT INTO is counted as a potential risk signal.  A note
    evidence records that true idempotency is a code-level property invisible
    to the agent and requires manual confirmation.  The LLM judge weighs both
    pieces and produces a verdict.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            merge_into = int(row.get("merge_into_stmts") or 0)
            replace_where = int(row.get("replace_where_stmts") or 0)
            insert_overwrite = int(row.get("insert_overwrite_stmts") or 0)
            insert_into = int(row.get("insert_into_stmts") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
        else:
            merge_into = 0
            replace_where = 0
            insert_overwrite = 0
            insert_into = 0
            total_stmts = 0

        idempotent_writes = merge_into + replace_where + insert_overwrite

        if total_stmts == 0:
            summary = (
                "No query-history rows found for the last 30 days"
                " — cannot assess transformation write patterns"
            )
        else:
            summary = (
                f"Write patterns (last 30 days): MERGE INTO={merge_into}, "
                f"REPLACE WHERE={replace_where}, INSERT OVERWRITE={insert_overwrite} "
                f"(idempotent-safe={idempotent_writes}); INSERT INTO={insert_into} (risk); "
                f"total statements={total_stmts}"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[
                {
                    "merge_into_stmts": merge_into,
                    "replace_where_stmts": replace_where,
                    "insert_overwrite_stmts": insert_overwrite,
                    "insert_into_stmts": insert_into,
                    "total_stmts": total_stmts,
                }
            ],
            ref=_IDEMPOTENCY_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_IDEMPOTENCY_NOTE,
            rows=[],
            ref=_IDEMPOTENCY_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
