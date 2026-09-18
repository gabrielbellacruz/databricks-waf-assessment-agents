"""Query materialization opportunity check (LLM-judged).

Answers:
  ANA-CO-05  Materialize expensive repeated queries

Signal:
  - Top repeated expensive SELECT queries from system.query.history
    (last 30 days, >= 3 executions, avg duration > 5 s).  Each such pattern is
    a candidate for a materialized view or pre-computed result.
  - REFRESH MATERIALIZED VIEW statements in query history as a proxy for
    existing materialized view usage.
  - A note on the limitation: listing all materialized views in detail requires
    per-catalog information_schema inspection beyond this check's scope.

The LLM weighs the volume of repeated expensive queries against evidence of
existing materialization to decide whether the practice is followed.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SLOW_REPEATED_SQL = (
    "SELECT statement_text, COUNT(*) AS execution_count, "
    "AVG(total_duration_ms) AS avg_duration_ms "
    "FROM system.query.history "
    "WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS "
    "AND statement_type = 'SELECT' "
    "AND total_duration_ms > 5000 "
    "GROUP BY statement_text "
    "HAVING COUNT(*) >= 3 "
    "ORDER BY execution_count * avg_duration_ms DESC "
    "LIMIT 10"
)

_MV_REFRESH_SQL = (
    "SELECT COUNT(*) AS refresh_count "
    "FROM system.query.history "
    "WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS "
    "AND statement_text ILIKE '%REFRESH MATERIALIZED VIEW%'"
)

_NOTE = (
    "Identifying all existing materialized views requires querying "
    "<catalog>.information_schema.tables WHERE table_type = 'MATERIALIZED VIEW' "
    "for each catalog in scope, which is outside the automated check boundary. "
    "The presence of REFRESH MATERIALIZED VIEW statements in system.query.history "
    "is used as a proxy for active materialized view usage."
)


@register(layer="analytics", question_ids=["ANA-CO-05"])
class QueryMaterializationCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        repeated_rows = ctx.sql.query(_SLOW_REPEATED_SQL)

        if repeated_rows:
            rpt_summary = (
                f"{len(repeated_rows)} repeated expensive SELECT pattern(s) found "
                f"(>=3 executions, avg >5s) in the last 30 days"
            )
        else:
            rpt_summary = (
                "No repeated expensive SELECT queries (>=3 executions, avg >5s) found "
                "in system.query.history for the last 30 days"
            )

        repeated_evidence = Evidence(
            kind="sql",
            summary=rpt_summary,
            detail=_SLOW_REPEATED_SQL,
            rows=[
                {
                    "statement_text": str(r.get("statement_text") or "")[:200],
                    "execution_count": r.get("execution_count"),
                    "avg_duration_ms": r.get("avg_duration_ms"),
                }
                for r in repeated_rows
            ],
            ref=(
                "https://docs.databricks.com/en/sql/language-manual/"
                "sql-ref-syntax-ddl-create-materialized-view.html"
            ),
        )

        mv_rows = ctx.sql.query(_MV_REFRESH_SQL)
        refresh_count = int((mv_rows[0].get("refresh_count") or 0) if mv_rows else 0)

        mv_evidence = Evidence(
            kind="sql",
            summary=(
                f"{refresh_count} REFRESH MATERIALIZED VIEW statement(s) found in "
                "query history (proxy for existing materialized view usage)"
            ),
            detail=_MV_REFRESH_SQL,
            rows=[{"refresh_count": refresh_count}],
            ref="https://docs.databricks.com/en/delta-live-tables/materialized-views.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
        )

        return [repeated_evidence, mv_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
