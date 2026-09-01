"""Workflow audit-changes check (LLM-judged).

Answers:
  ORC-SCP-04  Audit workflow permission and definition changes

Databricks captures job-related events in ``system.access.audit``
automatically. This check queries the diversity and volume of audit event
types (job create/update/delete/runNow, permission changes) over the last
30 days as a signal that the audit trail is active and covers both definition
and permission changes.

Presence and diversity of event types is positive evidence; an absence of any
job-related audit events is a risk signal (no activity, or audit not flowing
to the system table). Whether the team *reviews* audit logs cannot be inferred
from the event counts alone — the LLM judge provides context and a reviewer must
confirm review processes exist.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_JOB_EVENTS = """\
SELECT action_name,
       COUNT(*) AS event_count
FROM system.access.audit
WHERE service_name = 'jobs'
  AND event_date >= current_date() - INTERVAL 30 DAYS
GROUP BY action_name
ORDER BY event_count DESC
LIMIT 20\
"""

_SQL_PERM_EVENTS = """\
SELECT COUNT(*) AS total_perm_events,
       COUNT(DISTINCT action_name) AS distinct_perm_actions
FROM system.access.audit
WHERE service_name = 'permissions'
  AND action_name ILIKE '%job%'
  AND event_date >= current_date() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Audit events in system.access.audit prove that Databricks is capturing workflow "
    "activity, but the presence of events alone does not confirm that the team reviews "
    "or acts on audit logs. A reviewer should verify that audit log review is part of security "
    "operations and that retention meets compliance requirements."
)

_REF = "https://docs.databricks.com/en/administration-guide/account-settings/audit-log-delivery.html"


@register(layer="orchestration", question_ids=["ORC-SCP-04"])
class AuditChangesCheck(Check):
    """Assess audit coverage for workflow changes via system.access.audit event counts.

    Two queries: job-service events (definition create/update/delete/run) and
    permissions-service events for job ACL changes. The LLM judge weighs volume,
    diversity of action types, and a note about review-process visibility.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        job_rows = ctx.sql.query(_SQL_JOB_EVENTS)
        total_job_events = sum(int(r.get("event_count") or 0) for r in job_rows)
        distinct_job_actions = len(job_rows)

        if total_job_events > 0:
            job_summary = (
                f"{total_job_events} job-service audit events ({distinct_job_actions} distinct "
                "action types) in system.access.audit in the last 30 days"
            )
        else:
            job_summary = (
                "No job-service audit events found in system.access.audit for the last 30 days"
            )

        perm_rows = ctx.sql.query(_SQL_PERM_EVENTS)
        perm_total = int(perm_rows[0].get("total_perm_events") or 0) if perm_rows else 0
        perm_actions = int(perm_rows[0].get("distinct_perm_actions") or 0) if perm_rows else 0

        perm_summary = (
            f"{perm_total} job permission-change events ({perm_actions} distinct action types) "
            "in system.access.audit in the last 30 days"
        )

        job_evidence = Evidence(
            kind="sql",
            summary=job_summary,
            detail=_SQL_JOB_EVENTS,
            rows=job_rows[:20],
            ref=_REF,
        )

        perm_evidence = Evidence(
            kind="sql",
            summary=perm_summary,
            detail=_SQL_PERM_EVENTS,
            rows=[{"total_perm_events": perm_total, "distinct_perm_actions": perm_actions}],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [job_evidence, perm_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
