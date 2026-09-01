"""AI assistance in transformations check (LLM-judged).

Answers:
  PRO-IU-05  Use AI assistance to build transformations

Signal: query-history statements that call Databricks AI SQL functions
(``ai_query``, ``ai_classify``, ``ai_generate_text``, ``ai_analyze_sentiment``,
``ai_extract``, ``ai_fix``, ``ai_mask``, ``ai_similarity``, ``ai_translate``,
``ai_summarize``) over the last 30 days.  These built-in functions indicate
that the team has adopted AI assistance within SQL-based transformations.

A companion note records that AI assistance through notebooks, the Databricks
Assistant IDE integration, or external orchestration is not observable in
query history; the statement count is a lower bound, not a complete picture.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  SUM(CASE WHEN statement_text ILIKE '%ai_query(%'
           OR statement_text ILIKE '%ai_classify(%'
           OR statement_text ILIKE '%ai_generate_text(%'
           OR statement_text ILIKE '%ai_analyze_sentiment(%'
           OR statement_text ILIKE '%ai_extract(%'
           OR statement_text ILIKE '%ai_fix(%'
           OR statement_text ILIKE '%ai_mask(%'
           OR statement_text ILIKE '%ai_similarity(%'
           OR statement_text ILIKE '%ai_translate(%'
           OR statement_text ILIKE '%ai_summarize(%'
      THEN 1 ELSE 0 END) AS ai_sql_stmts,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "AI assistance through the Databricks Assistant (notebook IDE integration), "
    "external LLM calls in Python notebooks, or job-level AI orchestration is NOT "
    "observable via query history; only SQL-layer AI function calls are counted. "
    "The statement count is a lower bound on actual AI assistance usage. "
    "Manual confirmation needed for a complete picture."
)

_REF = "https://docs.databricks.com/en/large-language-models/ai-functions.html"


@register(layer="processing", question_ids=["PRO-IU-05"])
class ProcessingAiAssistanceCheck(Check):
    """Assess AI-assistance adoption in transformation workloads.

    Scans ``system.query.history`` (last 30 days) for statements that call
    Databricks built-in AI SQL functions (``ai_query``, ``ai_classify``, etc.).
    Their presence indicates that the team has adopted AI assistance within
    SQL-based transformations.  A note records that notebook-level and
    IDE-level AI assistance is not visible in query history.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            ai_sql_stmts = int(row.get("ai_sql_stmts") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
            pct = round(100.0 * ai_sql_stmts / total_stmts, 2) if total_stmts > 0 else 0.0
            summary = (
                f"{ai_sql_stmts} AI SQL function call(s) found "
                f"({pct}% of {total_stmts} total statements in the last 30 days)"
            )
            sql_evidence = Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=[{"ai_sql_stmts": ai_sql_stmts, "total_stmts": total_stmts}],
                ref=_REF,
            )
        else:
            sql_evidence = Evidence(
                kind="sql",
                summary="No query-history rows returned — cannot assess AI SQL function usage",
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
