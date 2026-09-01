"""AI capabilities for developer acceleration check (LLM-judged).

Answers:
  AI-IU-03  Use AI capabilities to accelerate development

Signal:
  1. system.billing.usage — SKUs containing 'ASSISTANT', 'GENIE', or 'AI_BI'
     indicate usage of Databricks AI assistance tooling (Databricks Assistant,
     AI/BI dashboards, Genie) that accelerates development.
  2. system.access.audit — events related to AI assistant interactions or
     Genie room queries indicate that teams are using AI to accelerate work.

Limitation note: Usage of AI coding assistants (Databricks Assistant inside
the IDE/notebook), Genie room queries, and AI/BI dashboard interactions may not
all appear in system.access.audit depending on workspace configuration and
audit-log settings. Billing SKUs are a proxy for feature adoption but do not
capture the depth of use.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_BILLING_SQL = (
    "SELECT COUNT(*) AS ai_assist_dbus,"
    " SUM(usage_quantity) AS total_assist_dbus"
    " FROM system.billing.usage"
    " WHERE LOWER(sku_name) LIKE '%assistant%'"
    "    OR LOWER(sku_name) LIKE '%genie%'"
    "    OR LOWER(sku_name) LIKE '%ai_bi%'"
    "    OR LOWER(sku_name) LIKE '%aibi%'"
)

_AUDIT_SQL = (
    "SELECT COUNT(*) AS ai_dev_events,"
    " COUNT(DISTINCT user_identity.email) AS distinct_users"
    " FROM system.access.audit"
    " WHERE action_name IN ("
    "  'genieSpaceQuery','genieSpaceCreate',"
    "  'assistantQuery','createAiFunction',"
    "  'aibiDashboardCreate','aibiDashboardUpdate'"
    " )"
    " AND CAST(event_time AS DATE) >= CURRENT_DATE - INTERVAL 30 DAYS"
)

_REF = (
    "https://docs.databricks.com/en/ai-assistant/index.html"
)

_ASSIST_LIMITATION = (
    "Databricks Assistant notebook/IDE interactions and Genie room usage may not"
    " all appear in system.access.audit depending on workspace configuration."
    " Billing SKUs for AI features vary by workspace plan tier and may be bundled"
    " rather than separately itemized."
)


@register(layer="ai", question_ids=["AI-IU-03"])
class AiDevelopmentAccelerationCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        billing_rows = ctx.sql.query(_BILLING_SQL)
        audit_rows = ctx.sql.query(_AUDIT_SQL)

        b = billing_rows[0] if billing_rows else {}
        assist_rows = int(b.get("ai_assist_dbus") or 0)
        assist_dbus = float(b.get("total_assist_dbus") or 0.0)

        a = audit_rows[0] if audit_rows else {}
        ai_events = int(a.get("ai_dev_events") or 0)
        distinct_users = int(a.get("distinct_users") or 0)

        billing_evidence = Evidence(
            kind="sql",
            summary=(
                f"{assist_rows} billing row(s) for AI assistance features"
                f" totalling {assist_dbus:.2f} DBUs"
                " (Assistant / Genie / AI/BI)"
            ),
            detail=_BILLING_SQL,
            rows=[{"ai_assist_dbus": assist_rows, "total_assist_dbus": assist_dbus}],
            ref=_REF,
        )
        audit_evidence = Evidence(
            kind="sql",
            summary=(
                f"{ai_events} AI development event(s) from {distinct_users}"
                " user(s) in the last 30 days (Genie, Assistant, AI/BI)"
            ),
            detail=_AUDIT_SQL,
            rows=[{"ai_dev_events": ai_events, "distinct_users": distinct_users}],
            ref=_REF,
        )
        limitation = Evidence(
            kind="uc_metadata",
            summary=_ASSIST_LIMITATION,
            detail=(
                "Check workspace feature enablement and user adoption by reviewing"
                " the Admin Console > Feature Enablement settings."
            ),
            ref=_REF,
        )
        return [billing_evidence, audit_evidence, limitation]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
