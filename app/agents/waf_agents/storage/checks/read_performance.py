"""Read-performance monitoring check (LLM-judged).

Answers:
  STO-PE-05  Monitor read performance on stored tables

The presence of read/SELECT query telemetry in system.query.history is evidence
that read performance *is* observable and can be monitored.  This check
aggregates SELECT statements over the last 30 days: count of queries, average
and maximum total_duration_ms, and the count of slow queries (>30 s) as a proxy
for performance visibility.

Aggregating this telemetry confirms that read-performance data exists in the
workspace; whether an active monitoring dashboard or alerting policy is in place
requires manual confirmation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SLOW_THRESHOLD_MS = 30_000

_SQL = f"""
SELECT
  COUNT(*) AS read_query_count,
  AVG(total_duration_ms) AS avg_duration_ms,
  MAX(total_duration_ms) AS max_duration_ms,
  SUM(CASE WHEN total_duration_ms > {_SLOW_THRESHOLD_MS} THEN 1 ELSE 0 END)
      AS slow_query_count
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS
  AND statement_type = 'SELECT'
""".strip()

_NOTE = (
    "The presence of SELECT query telemetry in system.query.history confirms that "
    "read-performance data is available and observable.  However, this alone does not "
    "confirm that an active monitoring dashboard, alerting policy, or SLA tracking is "
    "in place; manual confirmation is needed to assess whether read performance is actively "
    "monitored against defined thresholds."
)

_REF = "https://docs.databricks.com/en/optimizations/index.html"


@register(layer="storage", question_ids=["STO-PE-05"])
class ReadPerformanceCheck(Check):
    """Assess read-performance monitoring via aggregated SELECT query telemetry.

    Evidence is gathered from system.query.history over the last 30 days,
    filtering to SELECT statements: total query count, average and maximum
    total_duration_ms, and the count of slow queries (>30 s).  A note evidence
    records that telemetry presence does not equal active monitoring.  The LLM
    judge weighs both pieces.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            read_query_count = int(row.get("read_query_count") or 0)
            avg_ms_raw = row.get("avg_duration_ms")
            max_ms_raw = row.get("max_duration_ms")
            slow_query_count = int(row.get("slow_query_count") or 0)
            avg_ms = round(float(avg_ms_raw), 1) if avg_ms_raw is not None else None
            max_ms = int(max_ms_raw) if max_ms_raw is not None else None
        else:
            read_query_count = 0
            avg_ms = None
            max_ms = None
            slow_query_count = 0

        if read_query_count == 0:
            sql_summary = (
                "No SELECT statements found in system.query.history for the last 30 days"
                " — cannot assess read performance telemetry"
            )
        else:
            slow_pct = round(100.0 * slow_query_count / read_query_count, 1)
            dur_str = (
                f", avg={avg_ms}ms, max={max_ms}ms" if avg_ms is not None else ""
            )
            sql_summary = (
                f"{read_query_count} SELECT queries recorded in the last 30 days"
                f"{dur_str};"
                f" slow queries (>{_SLOW_THRESHOLD_MS // 1000}s): {slow_query_count}"
                f" ({slow_pct}%) — read-performance telemetry is available"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=sql_summary,
            detail=_SQL,
            rows=[
                {
                    "read_query_count": read_query_count,
                    "avg_duration_ms": avg_ms,
                    "max_duration_ms": max_ms,
                    "slow_query_count": slow_query_count,
                }
            ],
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
