"""Model endpoint access control check (LLM-judged).

Answers:
  ML-SCP-04  Control access to model endpoints

Signals:
1. ``system.access.audit``: serving endpoint permission-change events
   (updateEndpointPermissions, setServingEndpointPermissions) over the last
   30 days. Presence of permission-management events indicates active access
   governance on endpoints.

2. ``system.serving.endpoint_usage``: distinct endpoint names and aggregate
   request volume. Endpoints that are actively used but have no permission-
   change events in audit may lack access controls or rely on workspace-level
   defaults.

Limitation: serving endpoint ACL detail (which groups/users hold CAN_QUERY
or CAN_MANAGE) is NOT exposed in system.access.audit rows or
system.serving.endpoint_usage. Whether endpoints are restricted to specific
groups vs open to all workspace users requires checking the serving endpoint
REST API permissions. The agent's service principal cannot enumerate ACLs for
other teams' endpoints. A reviewer must verify via GET
/api/2.0/permissions/serving-endpoints/{id}.
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
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND (
    action_name ILIKE '%ServingEndpoint%Permission%'
    OR action_name ILIKE '%EndpointPermission%'
    OR action_name IN (
      'updateServingEndpointPermissions',
      'setServingEndpointPermissions',
      'getServingEndpointPermissions',
      'changeServingEndpointAcl'
    )
  )
GROUP BY action_name
ORDER BY event_count DESC\
"""

_ENDPOINT_USAGE_SQL = """\
SELECT COUNT(DISTINCT endpoint_name) AS active_endpoints,
       SUM(request_count) AS total_requests
FROM system.serving.endpoint_usage
WHERE window_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Serving endpoint ACL detail (which groups/users hold CAN_QUERY or CAN_MANAGE) is not "
    "exposed in system.access.audit rows or system.serving.endpoint_usage. Whether endpoints "
    "are restricted to specific groups vs open to all workspace users requires checking the "
    "serving endpoint REST API permissions. The agent's service principal cannot enumerate "
    "ACLs for other teams' endpoints. A reviewer must verify endpoint access controls via the "
    "Databricks UI or GET /api/2.0/permissions/serving-endpoints/{id}."
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/manage-serving-endpoints.html"


@register(layer="ml", question_ids=["ML-SCP-04"])
class EndpointAccessCheck(Check):
    """Assess model endpoint access control via permission-change audit events and usage.

    Evidence:
    - system.access.audit: endpoint permission-management event counts.
    - system.serving.endpoint_usage: active endpoint count and request volume.
    A note records that endpoint ACL detail is not visible to the agent and
    requires manual review via the REST API.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        perm_rows = ctx.sql.query(_PERM_EVENTS_SQL)
        usage_rows = ctx.sql.query(_ENDPOINT_USAGE_SQL)

        total_perm_events = sum(int(r.get("event_count") or 0) for r in perm_rows)

        if total_perm_events > 0:
            perm_summary = (
                f"{total_perm_events} serving endpoint permission-change event(s) "
                f"({len(perm_rows)} distinct action type(s)) in the last 30 days "
                "(system.access.audit)"
            )
        else:
            perm_summary = (
                "No serving endpoint permission-change events found in "
                "system.access.audit for the last 30 days"
            )

        perm_evidence = Evidence(
            kind="sql",
            summary=perm_summary,
            detail=_PERM_EVENTS_SQL,
            rows=perm_rows,
            ref=_REF,
        )

        u = usage_rows[0] if usage_rows else {}
        active_endpoints = int(u.get("active_endpoints") or 0)
        total_requests = int(u.get("total_requests") or 0)

        usage_summary = (
            f"{active_endpoints} active model endpoint(s) with {total_requests} "
            "total request(s) in the last 30 days (system.serving.endpoint_usage)"
        )

        usage_evidence = Evidence(
            kind="sql",
            summary=usage_summary,
            detail=_ENDPOINT_USAGE_SQL,
            rows=[{"active_endpoints": active_endpoints, "total_requests": total_requests}],
            ref="https://docs.databricks.com/en/admin/system-tables/serving.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [perm_evidence, usage_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
