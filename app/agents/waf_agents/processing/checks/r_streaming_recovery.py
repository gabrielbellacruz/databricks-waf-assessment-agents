"""Streaming transformation recovery check (LLM-judged).

Answers:
  PRO-R-03  Recover streaming transformations from failures

Whether a workspace can recover a streaming transformation after a checkpoint
failure is an operational practice: the right signals are whether streams *use*
a checkpointLocation (a prerequisite for restart) and whether the team has
actually tested the recovery procedure.  The first is observable in query
history; the second is not.  This check counts streaming and
checkpoint-related statements over the last 90 days, emits a SQL evidence block
with those counts, and a note evidence block explaining the observability gap.
The LLM judge weighs both.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  SUM(CASE WHEN statement_text ILIKE '%checkpointLocation%' THEN 1 ELSE 0 END)
      AS checkpoint_stmts,
  SUM(
    CASE
      WHEN statement_text ILIKE '%readStream%'
        OR statement_text ILIKE '%writeStream%'
        OR statement_text ILIKE '%trigger(%'
      THEN 1 ELSE 0
    END
  ) AS streaming_stmts,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 90 DAYS\
"""

_REF = "https://docs.databricks.com/en/structured-streaming/query-recovery.html"

_OBSERVABILITY_NOTE = (
    "Whether checkpoint-recovery has been *tested* as a procedure is an operational "
    "practice not observable in system tables; checkpoint usage in query history is "
    "only a proxy that streaming transformations are configured for restartability. "
    "Manual confirmation needed."
)


@register(layer="processing", question_ids=["PRO-R-03"])
class StreamingRecoveryCheck(Check):
    """Assess streaming-checkpoint recovery readiness via query history (90 days).

    Two pieces of evidence are emitted:
    1. SQL evidence: counts of statements containing ``checkpointLocation``,
       streaming keywords (``readStream``, ``writeStream``, ``trigger``), and
       total statements.  A non-zero ``checkpoint_stmts`` count is a positive
       signal that streams are configured for restartability.
    2. Note evidence: records that recovery *testing* is not observable in system
       tables; manual confirmation is required to assess this fully.

    The LLM judge weighs both pieces against WAF reliability guidance.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            checkpoint_stmts = int(row.get("checkpoint_stmts") or 0)
            streaming_stmts = int(row.get("streaming_stmts") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
        else:
            checkpoint_stmts = 0
            streaming_stmts = 0
            total_stmts = 0

        if total_stmts == 0:
            sql_summary = (
                "No query-history rows found for the last 90 days"
                " — cannot assess streaming checkpoint usage"
            )
        else:
            sql_summary = (
                f"checkpointLocation usage: {checkpoint_stmts} statements"
                f" (indicates restartable streams);"
                f" streaming statements (readStream/writeStream/trigger):"
                f" {streaming_stmts};"
                f" total statements: {total_stmts} (last 90 days)"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=sql_summary,
            detail=_SQL,
            rows=[
                {
                    "checkpoint_stmts": checkpoint_stmts,
                    "streaming_stmts": streaming_stmts,
                    "total_stmts": total_stmts,
                }
            ],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_OBSERVABILITY_NOTE,
            rows=[],
            ref=_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
