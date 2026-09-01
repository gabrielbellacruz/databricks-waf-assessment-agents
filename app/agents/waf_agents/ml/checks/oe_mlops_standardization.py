"""MLOps process standardization check (LLM-judged).

Answers:
  ML-OE-01  Standardize MLOps processes across teams

Signal: two audit signals from ``system.access.audit`` over the last 30 days.

1. Breadth of MLflow usage: distinct users who performed MLflow
   experiment/run/registry actions. Widespread adoption across many users
   is a positive proxy for standardization; concentration in one or two
   users suggests ad-hoc or siloed workflows.

2. Diversity of MLflow action types: how many distinct action categories
   (create experiment, log metric, register model, transition stage …) are
   present in the audit trail indicates how much of the MLflow lifecycle is
   actually being exercised.

Limitation: system tables do not expose whether teams share a common
project/repo structure, use shared MLflow tracking servers, or follow an
agreed promotion workflow. Breadth and diversity are proxies only; a reviewer
must confirm whether a written MLOps standard exists and is enforced.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_MLFLOW_BREADTH_SQL = """\
SELECT COUNT(DISTINCT user_identity.email) AS distinct_users,
       COUNT(*) AS total_events
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND (
    service_name IN ('mlflowAcl', 'mlflowEndpoints', 'mlflow')
    OR action_name ILIKE '%experiment%'
    OR action_name ILIKE '%mlflow%'
    OR action_name ILIKE '%modelVersion%'
    OR action_name ILIKE '%registeredModel%'
  )\
"""

_MLFLOW_ACTIONS_SQL = """\
SELECT action_name,
       COUNT(*) AS event_count
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND (
    service_name IN ('mlflowAcl', 'mlflowEndpoints', 'mlflow')
    OR action_name ILIKE '%experiment%'
    OR action_name ILIKE '%modelVersion%'
    OR action_name ILIKE '%registeredModel%'
  )
GROUP BY action_name
ORDER BY event_count DESC
LIMIT 20\
"""

_NOTE = (
    "system.access.audit reflects MLflow REST API activity but does not expose whether "
    "teams share a common MLflow tracking URI, use shared experiment namespaces, or follow "
    "a written MLOps standard. Breadth (distinct users) and action diversity are proxies for "
    "standardization but cannot confirm process alignment across teams. A reviewer must "
    "verify whether "
    "an MLOps runbook, shared experiment hierarchy, or CI/CD promotion workflow is in place."
)

_REF = "https://docs.databricks.com/en/mlflow/index.html"


@register(layer="ml", question_ids=["ML-OE-01"])
class MlopsStandardizationCheck(Check):
    """Assess MLOps standardization via breadth and diversity of MLflow audit events.

    Evidence:
    - system.access.audit: distinct users and total events for MLflow actions.
    - system.access.audit: distinct action types to gauge lifecycle coverage.
    A note records that true process standardization is not observable from
    system tables and requires manual confirmation.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        breadth_rows = ctx.sql.query(_MLFLOW_BREADTH_SQL)
        action_rows = ctx.sql.query(_MLFLOW_ACTIONS_SQL)

        b = breadth_rows[0] if breadth_rows else {}
        distinct_users = int(b.get("distinct_users") or 0)
        total_events = int(b.get("total_events") or 0)

        if total_events > 0:
            breadth_summary = (
                f"{total_events} MLflow-related audit event(s) from "
                f"{distinct_users} distinct user(s) in the last 30 days "
                "(system.access.audit)"
            )
        else:
            breadth_summary = (
                "No MLflow-related audit events found in system.access.audit "
                "for the last 30 days"
            )

        breadth_evidence = Evidence(
            kind="sql",
            summary=breadth_summary,
            detail=_MLFLOW_BREADTH_SQL,
            rows=[{"distinct_users": distinct_users, "total_events": total_events}],
            ref=_REF,
        )

        distinct_action_types = len(action_rows)
        total_action_events = sum(int(r.get("event_count") or 0) for r in action_rows)

        if distinct_action_types > 0:
            action_summary = (
                f"{total_action_events} MLflow event(s) across "
                f"{distinct_action_types} distinct action type(s) in the last 30 days"
            )
        else:
            action_summary = "No distinct MLflow action types found in system.access.audit"

        action_evidence = Evidence(
            kind="sql",
            summary=action_summary,
            detail=_MLFLOW_ACTIONS_SQL,
            rows=action_rows[:20],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [breadth_evidence, action_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
