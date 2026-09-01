"""Query performance monitoring check (LLM-judged).

Answers:
  ANA-PE-05  Monitor query performance and slow dashboards

Analytics workloads must have active performance monitoring: slow query
identification, duration trend tracking, and alerting when dashboards degrade.
The primary observable signal is ``system.query.history``, which records every
SQL warehouse statement with its total_duration_ms, execution_status, and
statement_type.

Aggregating SELECT queries over the last 30 days:
  - Total query count, average and p95-approximated maximum duration_ms.
  - Slow query count (>30 s) as a proxy for undetected performance regressions.
  - Failed query count as a signal for query-level instability.

The presence of this telemetry confirms that performance data IS available for
monitoring. Whether an active monitoring dashboard, alerting policy, or SLA
threshold is configured requires manual confirmation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SLOW_THRESHOLD_MS = 30_000

_SQL = (
    "SELECT "
    "COUNT(*) AS total_queries, "
    f"SUM(CASE WHEN total_duration_ms > {_SLOW_THRESHOLD_MS} THEN 1 ELSE 0 END) AS slow_queries, "
    "SUM(CASE WHEN execution_status = 'FAILED' THEN 1 ELSE 0 END) AS failed_queries, "
    "AVG(total_duration_ms) AS avg_duration_ms, "
    "MAX(total_duration_ms) AS max_duration_ms "
    "FROM system.query.history "
    "WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS "
    "AND statement_type = 'SELECT'"
)

_NOTE = (
    "The presence of SELECT query telemetry in system.query.history confirms that "
    "performance data (duration, status) is observable. However, telemetry availability "
    "alone does not confirm that an active monitoring dashboard, slow-query alert, or "
    "SLA threshold is in place. Whether slow queries are investigated and dashboard "
    "performance is tracked over time requires manual confirmation."
)

_REF = "https://docs.databricks.com/en/admin/system-tables/query-history.html"


@register(layer="analytics", question_ids=["ANA-PE-05"])
class QueryPerformanceCheck(Check):
    """Assess query performance monitoring via aggregated SELECT telemetry.

    Evidence is gathered from system.query.history over the last 30 days:
    total query count, average and max total_duration_ms, slow query count
    (>30 s), and failed query count. A note evidence records that telemetry
    presence does not equal active monitoring. The LLM judge weighs both.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            total_queries = int(row.get("total_queries") or 0)
            slow_queries = int(row.get("slow_queries") or 0)
            failed_queries = int(row.get("failed_queries") or 0)
            avg_ms_raw = row.get("avg_duration_ms")
            max_ms_raw = row.get("max_duration_ms")
            avg_ms = round(float(avg_ms_raw), 1) if avg_ms_raw is not None else None
            max_ms = int(max_ms_raw) if max_ms_raw is not None else None
        else:
            total_queries = 0
            slow_queries = 0
            failed_queries = 0
            avg_ms = None
            max_ms = None

        if total_queries == 0:
            sql_summary = (
                "No SELECT statements found in system.query.history for the last 30 days"
                " — cannot assess query performance telemetry"
            )
        else:
            slow_pct = round(100.0 * slow_queries / total_queries, 1)
            dur_str = (
                f", avg={avg_ms}ms, max={max_ms}ms"
                if avg_ms is not None
                else ""
            )
            sql_summary = (
                f"{total_queries} SELECT queries recorded in the last 30 days"
                f"{dur_str}; "
                f"slow queries (>{_SLOW_THRESHOLD_MS // 1000}s): {slow_queries}"
                f" ({slow_pct}%); "
                f"failed: {failed_queries}"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=sql_summary,
            detail=_SQL,
            rows=[{
                "total_queries": total_queries,
                "slow_queries": slow_queries,
                "failed_queries": failed_queries,
                "avg_duration_ms": avg_ms,
                "max_duration_ms": max_ms,
            }],
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
