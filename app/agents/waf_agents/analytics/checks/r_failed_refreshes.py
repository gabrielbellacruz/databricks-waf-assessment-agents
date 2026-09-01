"""Failed dataset refresh detection check (LLM-judged).

Answers:
  ANA-R-04  Detect and recover from failed dataset refreshes

Analytics datasets (materialized views, Dashboard datasets, scheduled queries)
must refresh reliably. Failures must be detected and either auto-retried or
alerted. The system tables provide partial signals:

  - ``system.query.history``: FAILED status on REFRESH or scheduled query
    statements shows whether refresh failures are occurring.
  - ``system.compute.warehouse_events``: warehouse-level error events (e.g.
    CREATE_ERROR, STOPPED unexpectedly) signal infrastructure instability
    that could cause refresh failures.

What is NOT directly observable: whether refresh failures trigger alerts (email,
Slack, PagerDuty), whether retry logic is configured, or whether an on-call
runbook exists. Manual confirmation is needed to assess recovery posture.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_FAILED_REFRESH_SQL = (
    "SELECT "
    "SUM(CASE WHEN execution_status = 'FAILED' THEN 1 ELSE 0 END) AS failed_stmts, "
    "SUM(CASE WHEN execution_status = 'FINISHED' THEN 1 ELSE 0 END) AS succeeded_stmts, "
    "COUNT(*) AS total_stmts "
    "FROM system.query.history "
    "WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS "
    "AND (statement_text ILIKE '%REFRESH%' OR statement_text ILIKE '%SCHEDULE%')"
)

_WAREHOUSE_ERROR_SQL = (
    "SELECT event_type, COUNT(*) AS cnt "
    "FROM system.compute.warehouse_events "
    "WHERE event_time >= current_timestamp() - INTERVAL 30 DAYS "
    "AND event_type ILIKE '%ERROR%' "
    "GROUP BY event_type "
    "ORDER BY cnt DESC"
)

_NOTE = (
    "Detecting and recovering from failed refreshes requires alerting (email/Slack/ "
    "PagerDuty on failure), retry configuration, and runbooks. Failure counts from "
    "query.history confirm that failures occur, but whether they are detected promptly "
    "and recovery is automated requires manual confirmation. Warehouse error events are a "
    "secondary signal for infrastructure-level failures."
)

_REF = "https://docs.databricks.com/en/sql/admin/alert.html"


@register(layer="analytics", question_ids=["ANA-R-04"])
class FailedRefreshesCheck(Check):
    """Assess whether failed dataset refreshes are detectable from system signals.

    Evidence:
      1. Failed vs succeeded REFRESH/SCHEDULE statement counts from query.history
         (last 30 days).
      2. Warehouse error events from warehouse_events (last 30 days).
      3. A note recording what cannot be determined from system tables (alerting,
         retry config, runbooks).
    The LLM judge weighs all three pieces.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        refresh_rows = ctx.sql.query(_FAILED_REFRESH_SQL)
        error_rows = ctx.sql.query(_WAREHOUSE_ERROR_SQL)

        if refresh_rows:
            row = refresh_rows[0]
            failed_stmts = int(row.get("failed_stmts") or 0)
            succeeded_stmts = int(row.get("succeeded_stmts") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
        else:
            failed_stmts = 0
            succeeded_stmts = 0
            total_stmts = 0

        if total_stmts == 0:
            refresh_summary = (
                "No REFRESH/SCHEDULE statements found in query.history for the last 30 days"
            )
        else:
            fail_pct = round(100.0 * failed_stmts / total_stmts, 1)
            refresh_summary = (
                f"Refresh/schedule statements (last 30 days): "
                f"{total_stmts} total, {succeeded_stmts} succeeded, "
                f"{failed_stmts} failed ({fail_pct}%)"
            )

        refresh_evidence = Evidence(
            kind="sql",
            summary=refresh_summary,
            detail=_FAILED_REFRESH_SQL,
            rows=[{
                "failed_stmts": failed_stmts,
                "succeeded_stmts": succeeded_stmts,
                "total_stmts": total_stmts,
            }],
            ref=_REF,
        )

        if error_rows:
            error_summary = (
                "Warehouse error events (last 30 days): "
                + ", ".join(f"{r['event_type']}={r['cnt']}" for r in error_rows[:10])
            )
        else:
            error_summary = (
                "No warehouse error events found in "
                "system.compute.warehouse_events for the last 30 days"
            )

        error_evidence = Evidence(
            kind="sql",
            summary=error_summary,
            detail=_WAREHOUSE_ERROR_SQL,
            rows=error_rows[:10],
            ref="https://docs.databricks.com/en/admin/system-tables/compute.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [refresh_evidence, error_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
