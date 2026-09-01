"""User feedback collection check (LLM-judged).

Answers:
  AI-OE-05  Collect and act on user feedback

Signals are very thin: no system table records whether an application collects
thumbs-up/thumbs-down ratings, free-text comments, or implicit feedback signals.

Proxy signals collected:
1. ``system.ai_gateway.usage``: presence of a dedicated ``feedback`` or
   ``rating`` endpoint (naming heuristic) and overall gateway traffic volume.
2. ``system.billing.usage``: presence of Databricks Apps SKU charges, which
   suggests that a user-facing app is deployed (apps can implement feedback UI).
3. ``system.access.audit``: app-service events as a further proxy for a
   deployed user-facing application.

A limitation note records that feedback collection, storage, and actioning
workflows are NOT observable from system tables and require manual confirmation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_GATEWAY_ENDPOINTS_SQL = """\
SELECT endpoint_name,
       COUNT(*) AS total_calls
FROM system.ai_gateway.usage
WHERE timestamp >= current_timestamp() - INTERVAL 30 DAYS
GROUP BY endpoint_name
ORDER BY total_calls DESC
LIMIT 20\
"""

_APPS_BILLING_SQL = """\
SELECT COUNT(*) AS app_billing_rows,
       SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE sku_name ILIKE '%APPS%'
  AND usage_date >= current_date() - INTERVAL 30 DAYS\
"""

_APP_AUDIT_SQL = """\
SELECT COUNT(*) AS app_audit_events,
       COUNT(DISTINCT action_name) AS distinct_actions
FROM system.access.audit
WHERE service_name = 'databricksapps'
  AND event_date >= current_date() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "User feedback collection (thumbs ratings, free-text comments, implicit click signals), "
    "feedback storage, and actioning workflows are NOT observable from Databricks system "
    "tables. Databricks Apps billing confirms a user-facing app is deployed, but not that "
    "it includes a feedback mechanism. Gateway endpoint names that contain 'feedback' or "
    "'rating' are a naming heuristic only. A reviewer must confirm whether feedback is collected, "
    "stored (e.g. in a Delta table), and reviewed to drive model improvements."
)

_REF = "https://docs.databricks.com/en/generative-ai/build-genai-apps.html"


@register(layer="ai", question_ids=["AI-OE-05"])
class UserFeedbackCheck(Check):
    """Assess user-feedback collection via Apps billing, audit events, and gateway names.

    Evidence:
    - system.ai_gateway.usage: endpoint names (feedback naming heuristic) and volume.
    - system.billing.usage: Databricks Apps DBU charges (proxy for deployed user app).
    - system.access.audit: databricksapps service events.
    A note records that feedback workflows are not observable in system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        gateway_rows = ctx.sql.query(_GATEWAY_ENDPOINTS_SQL)
        billing_rows = ctx.sql.query(_APPS_BILLING_SQL)
        audit_rows = ctx.sql.query(_APP_AUDIT_SQL)

        # Heuristic: endpoint names containing feedback-related tokens
        feedback_names = [
            r.get("endpoint_name", "")
            for r in gateway_rows
            if any(
                tok in str(r.get("endpoint_name", "")).lower()
                for tok in ["feedback", "rating", "thumbs", "review"]
            )
        ]
        if gateway_rows:
            gateway_summary = (
                f"{len(gateway_rows)} AI Gateway endpoint(s) active; "
                f"{len(feedback_names)} with feedback/rating name token(s) "
                "(heuristic, last 30 days)"
            )
        else:
            gateway_summary = "No rows in system.ai_gateway.usage for the last 30 days"

        gateway_evidence = Evidence(
            kind="sql",
            summary=gateway_summary,
            detail=_GATEWAY_ENDPOINTS_SQL,
            rows=gateway_rows[:20],
            ref="https://docs.databricks.com/en/ai-gateway/index.html",
        )

        app_billing_rows = int(
            (billing_rows[0].get("app_billing_rows") or 0) if billing_rows else 0
        )
        app_dbus = float(
            (billing_rows[0].get("total_dbus") or 0.0) if billing_rows else 0.0
        )
        billing_summary = (
            f"{app_billing_rows} Databricks Apps billing row(s), {app_dbus:.1f} DBUs "
            "in last 30 days — presence confirms a user-facing app is deployed"
            if app_billing_rows > 0
            else "No Databricks Apps billing rows found in the last 30 days"
        )

        billing_evidence = Evidence(
            kind="sql",
            summary=billing_summary,
            detail=_APPS_BILLING_SQL,
            rows=[{"app_billing_rows": app_billing_rows, "total_dbus": app_dbus}],
            ref="https://docs.databricks.com/en/apps/index.html",
        )

        app_events = int((audit_rows[0].get("app_audit_events") or 0) if audit_rows else 0)
        app_actions = int((audit_rows[0].get("distinct_actions") or 0) if audit_rows else 0)
        audit_summary = (
            f"{app_events} Databricks Apps audit event(s) ({app_actions} distinct action "
            "types) in system.access.audit for the last 30 days"
            if app_events > 0
            else "No Databricks Apps audit events found in system.access.audit for the last 30 days"
        )

        audit_evidence = Evidence(
            kind="sql",
            summary=audit_summary,
            detail=_APP_AUDIT_SQL,
            rows=[{"app_audit_events": app_events, "distinct_actions": app_actions}],
            ref="https://docs.databricks.com/en/admin/system-tables/audit.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [gateway_evidence, billing_evidence, audit_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
