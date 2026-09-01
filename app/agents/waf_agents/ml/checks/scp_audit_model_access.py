"""Model access and deployment audit check (LLM-judged).

Answers:
  ML-SCP-05  Audit model access and deployment changes

Signal: ``system.access.audit`` for two categories of ML lifecycle events
over the last 30 days.

1. Model registry mutations: registerModel, createModelVersion,
   transitionModelVersionStage, deleteRegisteredModel, updateRegisteredModel,
   setRegisteredModelAlias. Presence of these events confirms that model
   lifecycle changes are being captured in the audit trail.

2. Serving endpoint mutations: createServingEndpoint, updateServingEndpoint,
   deleteServingEndpoint, putServingEndpoint. These cover model deployment
   changes (which model version is live in production).

Volume and diversity of event types indicates breadth of audit coverage.
Complete absence of both categories is a risk signal: it may mean no models
have been registered / deployed, or that audit is not flowing to the system
table.

Limitation: the presence of audit events confirms that Databricks captures
ML lifecycle activity, but does not confirm that the team *reviews* or acts
on audit logs. Alert configuration for suspicious access (e.g. unexpected
stage transitions or endpoint deployments outside business hours) requires
Manual confirmation that an audit review process exists.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_REGISTRY_AUDIT_SQL = """\
SELECT action_name,
       COUNT(*) AS event_count
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND (
    action_name ILIKE '%registeredModel%'
    OR action_name ILIKE '%modelVersion%'
    OR action_name ILIKE '%transitionModel%'
    OR action_name IN (
      'registerModel', 'createRegisteredModel',
      'createModelVersion', 'transitionModelVersionStage',
      'deleteRegisteredModel', 'updateRegisteredModel',
      'setRegisteredModelAlias', 'deleteModelVersionTag'
    )
  )
GROUP BY action_name
ORDER BY event_count DESC
LIMIT 15\
"""

_SERVING_AUDIT_SQL = """\
SELECT action_name,
       COUNT(*) AS event_count,
       COUNT(DISTINCT user_identity.email) AS distinct_actors
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND action_name IN (
    'createServingEndpoint', 'updateServingEndpoint',
    'deleteServingEndpoint', 'putServingEndpoint',
    'createEndpoint', 'updateEndpoint', 'deleteEndpoint'
  )
GROUP BY action_name
ORDER BY event_count DESC\
"""

_NOTE = (
    "Presence of audit events confirms Databricks captures model lifecycle activity, but "
    "does not confirm that the team reviews or acts on these logs. Alert configuration for "
    "suspicious model access (unexpected stage transitions, off-hours deployments, "
    "unauthorized endpoint creation) is not observable from system tables. A reviewer must verify "
    "that audit log review is part of security operations and that log retention meets "
    "compliance requirements (e.g. 90/365 days)."
)

_REF = "https://docs.databricks.com/en/administration-guide/account-settings/audit-log-delivery.html"


@register(layer="ml", question_ids=["ML-SCP-05"])
class AuditModelAccessCheck(Check):
    """Assess model audit coverage via registry mutation and serving deployment events.

    Evidence:
    - system.access.audit: model registry action types and event counts.
    - system.access.audit: serving endpoint mutation events and distinct actors.
    A note records that log review processes and alert configuration require
    Manual confirmation.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        registry_rows = ctx.sql.query(_REGISTRY_AUDIT_SQL)
        serving_rows = ctx.sql.query(_SERVING_AUDIT_SQL)

        total_registry_events = sum(int(r.get("event_count") or 0) for r in registry_rows)

        if total_registry_events > 0:
            registry_summary = (
                f"{total_registry_events} model-registry mutation event(s) across "
                f"{len(registry_rows)} action type(s) in the last 30 days "
                "(system.access.audit)"
            )
        else:
            registry_summary = (
                "No model-registry mutation events found in "
                "system.access.audit for the last 30 days"
            )

        registry_evidence = Evidence(
            kind="sql",
            summary=registry_summary,
            detail=_REGISTRY_AUDIT_SQL,
            rows=registry_rows[:15],
            ref=_REF,
        )

        total_serving_events = sum(int(r.get("event_count") or 0) for r in serving_rows)
        distinct_serving_actors = (
            max((int(r.get("distinct_actors") or 0) for r in serving_rows), default=0)
        )

        if total_serving_events > 0:
            serving_summary = (
                f"{total_serving_events} serving endpoint deployment/mutation event(s) "
                f"from {distinct_serving_actors} distinct actor(s) in the last 30 days"
            )
        else:
            serving_summary = (
                "No serving endpoint mutation events found in "
                "system.access.audit for the last 30 days"
            )

        serving_evidence = Evidence(
            kind="sql",
            summary=serving_summary,
            detail=_SERVING_AUDIT_SQL,
            rows=serving_rows,
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [registry_evidence, serving_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
