"""AI endpoint access scoping check (LLM-judged).

Answers:
  AI-SCP-03  Scope AI endpoint access and credentials

Signals:
1. ``system.access.audit``: serving endpoint permission-change events (updates
   to endpoint ACLs) over the last 30 days — evidence that access is actively
   managed.
2. ``system.ai_gateway.usage``: count of distinct requesters per endpoint as a
   proxy for access breadth (few distinct requesters suggest tight scoping; many
   may indicate broad/open access).
3. ``system.access.audit``: serving endpoint permission-related actions
   (grantServingEndpointPermission, revokeServingEndpointPermission).

Limitations noted:
- Unity Catalog function/table grants that back AI endpoints are not captured
  in these queries.
- Service-principal credential rotation policy and secrets management for
  endpoint credentials are not observable from system tables.
- Fine-grained permission details (which principals have which roles) require
  REST API calls the agent's SP may not have access to.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_PERM_EVENTS_SQL = """\
SELECT action_name,
       COUNT(*) AS event_count
FROM system.access.audit
WHERE service_name IN ('serving', 'mlflowEndpoints', 'permissions')
  AND (
      action_name ILIKE '%Permission%'
      OR action_name ILIKE '%grant%'
      OR action_name ILIKE '%revoke%'
      OR action_name ILIKE '%acl%'
  )
  AND event_date >= current_date() - INTERVAL 30 DAYS
GROUP BY action_name
ORDER BY event_count DESC
LIMIT 15\
"""

_REQUESTER_BREADTH_SQL = """\
SELECT endpoint_name,
       COUNT(DISTINCT requester) AS distinct_requesters,
       COUNT(*) AS total_calls
FROM system.ai_gateway.usage
WHERE timestamp >= current_timestamp() - INTERVAL 30 DAYS
GROUP BY endpoint_name
ORDER BY total_calls DESC
LIMIT 15\
"""

_NOTE = (
    "Serving endpoint permission-change events in system.access.audit confirm that "
    "access control is actively managed, but the current permission state (which "
    "principals have which roles on each endpoint) is not exposed in system tables "
    "and requires REST API inspection. Distinct requester counts from AI Gateway "
    "are a breadth proxy only — a low count may still include overly broad service "
    "principals. Credential management (service-principal rotation, secret scopes "
    "for endpoint tokens) is not observable from system tables. A reviewer must review "
    "endpoint ACLs directly and confirm least-privilege principles are applied."
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/manage-serving-endpoint-permissions.html"


@register(layer="ai", question_ids=["AI-SCP-03"])
class EndpointAccessCheck(Check):
    """Assess AI endpoint access scoping via permission events and requester breadth.

    Evidence:
    - system.access.audit: permission-change events on serving endpoints.
    - system.ai_gateway.usage: distinct requester counts per endpoint.
    A note records that current ACL state and credential management are not
    observable from system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        perm_rows = ctx.sql.query(_PERM_EVENTS_SQL)
        requester_rows = ctx.sql.query(_REQUESTER_BREADTH_SQL)

        total_perm_events = sum(int(r.get("event_count") or 0) for r in perm_rows)
        if total_perm_events > 0:
            perm_summary = (
                f"{total_perm_events} serving-endpoint permission event(s) across "
                f"{len(perm_rows)} distinct action type(s) in system.access.audit "
                "(last 30 days) — access control is being actively managed"
            )
        else:
            perm_summary = (
                "No serving-endpoint permission-change events found in "
                "system.access.audit for the last 30 days — access control "
                "activity is not observable"
            )

        perm_evidence = Evidence(
            kind="sql",
            summary=perm_summary,
            detail=_PERM_EVENTS_SQL,
            rows=perm_rows,
            ref="https://docs.databricks.com/en/admin/system-tables/audit.html",
        )

        if requester_rows:
            max_requesters = max(int(r.get("distinct_requesters") or 0) for r in requester_rows)
            requester_summary = (
                f"{len(requester_rows)} AI Gateway endpoint(s) with distinct requester "
                f"counts; max distinct requesters on one endpoint: {max_requesters} "
                "(last 30 days)"
            )
        else:
            max_requesters = 0
            requester_summary = "No requester data in system.ai_gateway.usage for the last 30 days"

        requester_evidence = Evidence(
            kind="sql",
            summary=requester_summary,
            detail=_REQUESTER_BREADTH_SQL,
            rows=requester_rows[:15],
            ref="https://docs.databricks.com/en/ai-gateway/index.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [perm_evidence, requester_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
