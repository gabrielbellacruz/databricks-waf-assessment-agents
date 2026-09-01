"""Analytics query audit coverage check (LLM-judged).

Answers:
  ANA-SCP-04  Audit analytics access and queries

The audit trail for analytics queries lives in two places:
  * system.query.history — all SQL executed on warehouses (user, statement,
    status, duration). This is the primary source of per-query attribution.
  * system.access.audit — workspace-level security events including
    commandRun/commandFinish actions that mark query execution.

This check collects evidence of both to establish whether a meaningful audit
record exists. The LLM judge weighs both signals and a note about the limits
of automated observation (review processes require manual confirmation).
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_QUERY_HISTORY_SQL = """\
SELECT COUNT(*) AS total_queries,
       COUNT(DISTINCT executed_by) AS distinct_users,
       SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed_queries
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_AUDIT_EVENTS_SQL = """\
SELECT COUNT(*) AS audit_event_count,
       COUNT(DISTINCT user_identity_email) AS distinct_users_audited
FROM system.access.audit
WHERE event_time >= current_timestamp() - INTERVAL 30 DAYS
  AND action_name IN (
        'runCommand', 'commandFinish',
        'listEndpointQueries', 'getQueryResult'
  )\
"""

_NOTE = (
    "system.query.history is the primary query audit log for Databricks SQL — every "
    "warehouse query is recorded with user identity, statement text, and status. "
    "system.access.audit captures workspace-level security events. "
    "Whether the audit logs are actively reviewed for sensitive-dataset accesses "
    "cannot be determined from the tables alone; manual confirmation is recommended."
)

_REF = (
    "https://docs.databricks.com/en/administration-guide/account-settings/audit-log.html"
)


@register(layer="analytics", question_ids=["ANA-SCP-04"])
class QueryAuditCheck(Check):
    """Assess query audit coverage via system.query.history and system.access.audit.

    Evidence from both tables is gathered and a note records the limits of
    automated observation (active review requires manual confirmation).
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        qh_rows = ctx.sql.query(_QUERY_HISTORY_SQL)
        if qh_rows:
            total_q = int(qh_rows[0].get("total_queries") or 0)
            distinct_users = int(qh_rows[0].get("distinct_users") or 0)
            failed_q = int(qh_rows[0].get("failed_queries") or 0)
        else:
            total_q = 0
            distinct_users = 0
            failed_q = 0

        qh_summary = (
            f"{total_q} queries run by {distinct_users} distinct user(s) in the last "
            f"30 days captured in system.query.history ({failed_q} failed)"
        )

        ae_rows = ctx.sql.query(_AUDIT_EVENTS_SQL)
        if ae_rows:
            event_count = int(ae_rows[0].get("audit_event_count") or 0)
            audited_users = int(ae_rows[0].get("distinct_users_audited") or 0)
        else:
            event_count = 0
            audited_users = 0

        ae_summary = (
            f"{event_count} query-related audit event(s) for {audited_users} user(s) "
            f"in system.access.audit (last 30 days)"
        )

        return [
            Evidence(
                kind="sql",
                summary=qh_summary,
                detail=_QUERY_HISTORY_SQL,
                rows=[
                    {
                        "total_queries": total_q,
                        "distinct_users": distinct_users,
                        "failed_queries": failed_q,
                    }
                ],
                ref="https://docs.databricks.com/en/monitoring/system-tables/query-history.html",
            ),
            Evidence(
                kind="sql",
                summary=ae_summary,
                detail=_AUDIT_EVENTS_SQL,
                rows=[
                    {
                        "audit_event_count": event_count,
                        "distinct_users_audited": audited_users,
                    }
                ],
                ref="https://docs.databricks.com/en/monitoring/system-tables/audit.html",
            ),
            Evidence(
                kind="note",
                summary=_NOTE,
                rows=[],
                ref=_REF,
            ),
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
