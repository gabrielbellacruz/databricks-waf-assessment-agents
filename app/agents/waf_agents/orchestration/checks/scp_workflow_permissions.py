"""Workflow permission scoping check (LLM-judged).

Answers:
  ORC-SCP-02  Scope workflow permissions to only required resources

No system-table column directly records the ACL or permission level of a
job, nor whether a service principal has least-privilege access to compute
and data resources. The best observable proxies are:

  1. ``system.lakeflow.jobs`` - the number of distinct run_as identities
     relative to the total job count: a single SP running all jobs suggests
     over-broad privileges; many granular SPs suggest better scoping.
  2. ``system.access.audit`` - permission-change events for jobs in the last
     90 days: active permission management indicates the team is reviewing ACLs.

Both signals are indirect; the LLM judge weighs them together with a note
recording the visibility limitation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_IDENTITIES = """\
SELECT COUNT(*) AS total_jobs,
       COUNT(DISTINCT run_as) AS distinct_identities,
       SUM(CASE WHEN run_as IS NOT NULL AND run_as <> '' AND run_as NOT LIKE '%@%'
           THEN 1 ELSE 0 END) AS sp_jobs
FROM system.lakeflow.jobs
WHERE delete_time IS NULL\
"""

_SQL_PERM_EVENTS = """\
SELECT COUNT(*) AS perm_change_events
FROM system.access.audit
WHERE service_name = 'permissions'
  AND action_name ILIKE '%job%'
  AND event_date >= current_date() - INTERVAL 90 DAYS\
"""

_NOTE = (
    "Direct ACL inspection for jobs requires admin-level API access that is not "
    "available to the agent's service principal. The distinct-identity ratio is a "
    "weak proxy: multiple SPs can still be over-privileged, and a single SP could "
    "be correctly scoped. A reviewer must verify that each workflow's run_as identity has "
    "only the permissions it requires (cluster policies, Unity Catalog grants, etc.)."
)

_REF = "https://docs.databricks.com/en/security/auth/access-control/jobs-acl.html"


@register(layer="orchestration", question_ids=["ORC-SCP-02"])
class WorkflowPermissionsCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        id_rows = ctx.sql.query(_SQL_IDENTITIES)
        row = id_rows[0] if id_rows else {"total_jobs": 0, "distinct_identities": 0, "sp_jobs": 0}
        total_jobs = int(row.get("total_jobs") or 0)
        distinct = int(row.get("distinct_identities") or 0)
        sp_jobs = int(row.get("sp_jobs") or 0)

        if total_jobs > 0:
            id_summary = (
                f"{distinct} distinct run_as identities across {total_jobs} jobs "
                f"({sp_jobs} using service principals)"
            )
        else:
            id_summary = "No jobs found in system.lakeflow.jobs"

        perm_rows = ctx.sql.query(_SQL_PERM_EVENTS)
        perm_events = int(perm_rows[0].get("perm_change_events") or 0) if perm_rows else 0

        identity_evidence = Evidence(
            kind="sql",
            summary=id_summary,
            detail=_SQL_IDENTITIES,
            rows=[{"total_jobs": total_jobs, "distinct_identities": distinct, "sp_jobs": sp_jobs}],
            ref=_REF,
        )

        perm_evidence = Evidence(
            kind="sql",
            summary=(
                f"{perm_events} job permission-change events in system.access.audit "
                "in the last 90 days"
            ),
            detail=_SQL_PERM_EVENTS,
            rows=[{"perm_change_events": perm_events}],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [identity_evidence, perm_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
