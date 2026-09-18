"""Dashboard staleness and alert check (LLM-judged).

Answers:
  ANA-OE-04  Alert on stale or broken dashboards

Dashboard staleness-alert configuration is not exposed in system tables.
The observable proxy is the rate of failed and canceled queries from
system.query.history (last 30 days): persistent failures that go unaddressed
suggest alerting is absent or insufficient. A note records that alert wiring
requires manual confirmation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT COUNT(*) AS total_queries,
       SUM(CASE WHEN execution_status = 'FAILED' THEN 1 ELSE 0 END) AS failed_queries,
       SUM(CASE WHEN execution_status = 'CANCELED' THEN 1 ELSE 0 END) AS canceled_queries
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_ALERT_NOTE = (
    "Dashboard staleness alerts (e.g. Databricks SQL Alerts or external notification channels) "
    "are not observable through system tables. The query failure rate from system.query.history "
    "is used as a proxy — persistent failures that go unaddressed suggest alerting is absent "
    "or insufficient. Manual confirmation of alert configuration is required."
)

_ALERT_REF = "https://docs.databricks.com/en/sql/user/alerts/index.html"


@register(layer="analytics", question_ids=["ANA-OE-04"])
class DashboardAlertsCheck(Check):
    """Assess dashboard alert coverage via recent query failure rate.

    Evidence is gathered from system.query.history (last 30 days). A note evidence
    records that alert configuration is not visible to the agent and must be
    Confirmed manually.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            total = int(rows[0].get("total_queries") or 0)
            failed = int(rows[0].get("failed_queries") or 0)
            canceled = int(rows[0].get("canceled_queries") or 0)
        else:
            total = 0
            failed = 0
            canceled = 0

        if total > 0:
            failure_pct = round(100.0 * failed / total, 1)
            summary = (
                f"{failed} of {total} queries failed and {canceled} were canceled "
                f"in the last 30 days ({failure_pct}% failure rate)"
            )
        else:
            failure_pct = 0.0
            summary = "No queries found in system.query.history for the last 30 days"

        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=[
                    {
                        "total_queries": total,
                        "failed_queries": failed,
                        "canceled_queries": canceled,
                        "failure_pct": failure_pct,
                    }
                ],
                ref="https://docs.databricks.com/en/monitoring/system-tables/query-history.html",
            ),
            Evidence(
                kind="note",
                summary=_ALERT_NOTE,
                rows=[],
                ref=_ALERT_REF,
            ),
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
