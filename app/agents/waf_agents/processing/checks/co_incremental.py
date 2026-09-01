"""Incremental-processing check (LLM-judged).

Answers:
  PRO-CO-04  Prefer incremental over full-reprocessing

There is no single metric that proves transformation pipelines always
process incrementally. The best proxy is the *mix of write patterns* in
recent query history: MERGE INTO, APPLY CHANGES INTO (DLT CDC), and
foreachBatch are incremental signals; INSERT OVERWRITE, CREATE OR REPLACE
TABLE, and TRUNCATE TABLE / INSERT indicate full-reprocessing patterns
that are costly at scale and defeat incremental design.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  SUM(CASE WHEN statement_text ILIKE '%MERGE INTO%'
      THEN 1 ELSE 0 END) AS merge_stmts,
  SUM(CASE WHEN statement_text ILIKE '%APPLY CHANGES INTO%'
      THEN 1 ELSE 0 END) AS apply_changes,
  SUM(CASE WHEN statement_text ILIKE '%foreachBatch%'
      THEN 1 ELSE 0 END) AS foreach_batch,
  SUM(
    CASE
      WHEN statement_text ILIKE '%INSERT OVERWRITE%'
        OR statement_text ILIKE '%CREATE OR REPLACE TABLE%'
        OR statement_text ILIKE '%TRUNCATE TABLE%'
      THEN 1 ELSE 0
    END
  ) AS full_reprocess,
  COUNT(*) AS total
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_REF = "https://docs.databricks.com/en/delta/delta-streaming.html"


@register(layer="processing", question_ids=["PRO-CO-04"])
class ProcessingIncrementalCheck(Check):
    """Count incremental vs full-reprocessing write patterns in query history.

    Incremental signals: MERGE INTO, APPLY CHANGES INTO (DLT CDC), foreachBatch.
    Full-reprocessing anti-patterns: INSERT OVERWRITE, CREATE OR REPLACE TABLE,
    TRUNCATE TABLE / INSERT.
    The LLM judge weighs the mix against WAF best-practice guidance.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        if not rows:
            return [
                Evidence(
                    kind="sql",
                    summary=(
                        "No query-history rows returned for the last 30 days"
                        " — cannot assess incremental vs full-reprocessing patterns"
                    ),
                    detail=_SQL,
                    rows=[],
                    ref=_REF,
                )
            ]

        row = rows[0]
        merge_stmts = int(row.get("merge_stmts") or 0)
        apply_changes = int(row.get("apply_changes") or 0)
        foreach_batch = int(row.get("foreach_batch") or 0)
        full_reprocess = int(row.get("full_reprocess") or 0)
        total = int(row.get("total") or 0)
        incremental = merge_stmts + apply_changes + foreach_batch

        summary = (
            f"Incremental patterns (merge={merge_stmts}, apply_changes={apply_changes},"
            f" foreachBatch={foreach_batch}) total={incremental};"
            f" full-reprocess anti-patterns={full_reprocess};"
            f" total statements={total} (last 30 days)"
        )
        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=[
                    {
                        "merge_stmts": merge_stmts,
                        "apply_changes": apply_changes,
                        "foreach_batch": foreach_batch,
                        "full_reprocess": full_reprocess,
                        "total": total,
                    }
                ],
                ref=_REF,
            )
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
