"""Natural-language analytics usage check (LLM-judged).

Answers:
  ANA-IU-04  Use natural-language analytics where helpful

Signals:
  * ``system.query.history`` — count of queries in the last 30 days that contain
    Databricks AI SQL function calls (``ai_query``, ``ai_generate``,
    ``ai_analyze_sentiment``, ``ai_classify``, ``ai_summarize``) in their statement
    text.  These functions embed natural-language capabilities directly in SQL.
  * ``system.query.history`` — count of queries whose statement text contains
    patterns associated with Genie-generated SQL (``-- genie`` comment prefix or
    ``ai_assistant`` references).  Genie Spaces execute as warehouse queries, so
    their SQL may appear here.

Limitation: Genie Spaces (conversational natural-language analytics) is not
directly observable as a distinct object type in system tables.  The SQL it
generates appears in query.history, but cannot be reliably distinguished from
hand-written SQL in all cases.  A zero count may mean NL analytics is not in use,
or that the workspace uses Genie without detectable SQL markers.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_AI_FUNCTION_SQL = (
    "SELECT COUNT(*) AS ai_function_queries"
    " FROM system.query.history"
    " WHERE (statement_text ILIKE '%ai_query%'"
    "   OR statement_text ILIKE '%ai_generate%'"
    "   OR statement_text ILIKE '%ai_analyze_sentiment%'"
    "   OR statement_text ILIKE '%ai_classify%'"
    "   OR statement_text ILIKE '%ai_summarize%')"
    " AND start_time > current_timestamp() - INTERVAL 30 DAYS"
)

_GENIE_SIGNAL_SQL = (
    "SELECT COUNT(*) AS genie_style_queries"
    " FROM system.query.history"
    " WHERE (LOWER(statement_text) LIKE '%-- genie%'"
    "   OR LOWER(statement_text) LIKE '%ai_assistant%'"
    "   OR LOWER(statement_text) LIKE '%natural language%')"
    " AND start_time > current_timestamp() - INTERVAL 30 DAYS"
)

_NL_LIMITATION = (
    "Genie Spaces (natural-language analytics) are not directly queryable from"
    " system.information_schema or system.access; only the SQL queries they"
    " generate appear in system.query.history, and those cannot be reliably"
    " distinguished from hand-written queries in all cases."
)

_REF = "https://docs.databricks.com/en/genie/index.html"


@register(layer="analytics", question_ids=["ANA-IU-04"])
class NaturalLanguageAnalyticsCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        ai_rows = ctx.sql.query(_AI_FUNCTION_SQL)
        genie_rows = ctx.sql.query(_GENIE_SIGNAL_SQL)

        ai_queries = int((ai_rows[0].get("ai_function_queries") or 0) if ai_rows else 0)
        genie_queries = int(
            (genie_rows[0].get("genie_style_queries") or 0) if genie_rows else 0
        )

        ai_evidence = Evidence(
            kind="sql",
            summary=(
                f"{ai_queries} query(ies) using Databricks AI SQL functions"
                " (ai_query/ai_generate/ai_analyze_sentiment/ai_classify/ai_summarize)"
                " in the last 30 days"
            ),
            detail=_AI_FUNCTION_SQL,
            rows=ai_rows[:5],
            ref=_REF,
        )
        genie_evidence = Evidence(
            kind="sql",
            summary=(
                f"{genie_queries} query(ies) with Genie/AI-assistant style markers"
                " in statement text (last 30 days)"
            ),
            detail=_GENIE_SIGNAL_SQL,
            rows=genie_rows[:5],
            ref=_REF,
        )
        limitation_evidence = Evidence(
            kind="uc_metadata",
            summary=_NL_LIMITATION,
            detail=(
                "To audit Genie Spaces directly, review the Genie Spaces list in the"
                " Databricks workspace UI or via the Genie Spaces REST API."
            ),
            ref=_REF,
        )
        return [ai_evidence, genie_evidence, limitation_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
