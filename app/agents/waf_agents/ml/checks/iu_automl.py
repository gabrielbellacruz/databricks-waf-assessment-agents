"""AutoML usage check (LLM-judged).

Answers:
  ML-IU-04  Use AutoML to accelerate baselines

Signals:
  * ``system.access.audit`` — count of AutoML-related audit events in the last 90 days
    (action_name or service_name containing 'automl'). Presence indicates that AutoML
    has been invoked to generate baseline models.
  * ``system.billing.usage`` — count of AutoML-specific SKU rows in the last 90 days.
    Databricks AutoML runs incur compute charges under identifiable SKUs.
  * Note: AutoML invocations through the Databricks UI or via the Python API may not
    always produce distinct 'automl' audit events in all workspace configurations. Absence
    of AutoML audit events does not conclusively prove AutoML is unused — manual confirmation
    is recommended. MLflow experiment artifacts from AutoML runs are not visible in
    system tables.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 90

# AutoML audit events in the window.
_AUTOML_AUDIT_SQL = (
    "SELECT COUNT(*) AS automl_events, "
    "COUNT(DISTINCT user_identity.email) AS distinct_automl_users "
    "FROM system.access.audit "
    f"WHERE event_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS "
    "  AND (LOWER(action_name) LIKE '%automl%' "
    "       OR LOWER(service_name) LIKE '%automl%')"
)

# AutoML billing SKU usage in the window.
_AUTOML_BILLING_SQL = (
    "SELECT COUNT(*) AS automl_usage_events, "
    "SUM(usage_quantity) AS automl_dbus "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "  AND sku_name ILIKE '%AUTOML%'"
)

_NOTE = (
    f"AutoML audit events in system.access.audit are available for the last {_WINDOW_DAYS} days "
    "but coverage depends on workspace audit log configuration. AutoML invocations through the "
    "UI may not generate distinct 'automl' service_name events in all runtime versions. "
    "MLflow experiment artifacts and trial results from AutoML runs are not in system tables. "
    "Zero events does not conclusively prove AutoML is unused — manual confirmation needed."
)

_REF = "https://docs.databricks.com/en/machine-learning/automl/index.html"


@register(layer="ml", question_ids=["ML-IU-04"])
class MlAutomlCheck(Check):
    """LLM-judged check for ML-IU-04: AutoML usage to accelerate baselines."""

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        audit_rows = ctx.sql.query(_AUTOML_AUDIT_SQL)
        billing_rows = ctx.sql.query(_AUTOML_BILLING_SQL)

        arow = audit_rows[0] if audit_rows else {}
        automl_events = int(arow.get("automl_events") or 0)
        distinct_automl_users = int(arow.get("distinct_automl_users") or 0)

        brow = billing_rows[0] if billing_rows else {}
        automl_usage_events = int(brow.get("automl_usage_events") or 0)

        audit_evidence = Evidence(
            kind="sql",
            summary=(
                f"{automl_events} AutoML audit event(s) by {distinct_automl_users} "
                f"distinct user(s) in the last {_WINDOW_DAYS} days "
                "(system.access.audit, service/action_name contains 'automl')"
            ),
            detail=_AUTOML_AUDIT_SQL,
            rows=[
                {
                    "automl_events": automl_events,
                    "distinct_automl_users": distinct_automl_users,
                }
            ],
            ref=_REF,
        )
        billing_evidence = Evidence(
            kind="sql",
            summary=(
                f"{automl_usage_events} AutoML billing record(s) (AUTOML SKU) "
                f"in the last {_WINDOW_DAYS} days"
            ),
            detail=_AUTOML_BILLING_SQL,
            rows=[{"automl_usage_events": automl_usage_events}],
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )
        return [audit_evidence, billing_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
