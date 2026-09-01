"""Incremental-ingestion check (LLM-judged).

Answers:
  ING-PE-02  Ingest incrementally rather than reprocessing full loads

There is no single metric that proves a workspace always ingests
incrementally. The best proxy is the *mix of write patterns* in recent
query history: statements that use cloud_files (Auto Loader), MERGE INTO,
or COPY INTO are incremental signals; INSERT OVERWRITE and CREATE OR
REPLACE TABLE indicate full-reload patterns that defeat incremental
design. This check counts each pattern over the last 30 days and lets
the LLM judge weigh them.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """
SELECT
  SUM(CASE WHEN statement_text ILIKE '%cloud_files%'
      THEN 1 ELSE 0 END) AS autoloader,
  SUM(CASE WHEN statement_text ILIKE '%MERGE INTO%'
      THEN 1 ELSE 0 END) AS merge_stmts,
  SUM(CASE WHEN statement_text ILIKE '%COPY INTO%'
      THEN 1 ELSE 0 END) AS copy_into,
  SUM(
    CASE
      WHEN statement_text ILIKE '%INSERT OVERWRITE%'
        OR statement_text ILIKE '%CREATE OR REPLACE TABLE%'
      THEN 1 ELSE 0
    END
  ) AS full_reload,
  COUNT(*) AS total
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS
""".strip()

_REF = "https://docs.databricks.com/en/ingestion/index.html"


@register(layer="ingestion", question_ids=["ING-PE-02"])
class IncrementalIngestionCheck(Check):
    """Count incremental vs full-reload write patterns in query history.

    Incremental signals: cloud_files (Auto Loader), MERGE INTO, COPY INTO.
    Full-reload anti-pattern: INSERT OVERWRITE, CREATE OR REPLACE TABLE.
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
                        " — cannot assess incremental vs full-reload patterns"
                    ),
                    detail=_SQL,
                    rows=[],
                    ref=_REF,
                )
            ]

        row = rows[0]
        autoloader = int(row.get("autoloader") or 0)
        merge_stmts = int(row.get("merge_stmts") or 0)
        copy_into = int(row.get("copy_into") or 0)
        full_reload = int(row.get("full_reload") or 0)
        total = int(row.get("total") or 0)
        incremental = autoloader + merge_stmts + copy_into

        summary = (
            f"Incremental patterns (autoloader={autoloader}, merge={merge_stmts},"
            f" copy_into={copy_into}) total={incremental};"
            f" full-reload anti-patterns={full_reload};"
            f" total statements={total} (last 30 days)"
        )
        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=[
                    {
                        "autoloader": autoloader,
                        "merge_stmts": merge_stmts,
                        "copy_into": copy_into,
                        "full_reload": full_reload,
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
