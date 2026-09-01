"""Model drift and performance monitoring check (LLM-judged).

Answers:
  ML-OE-05  Monitor models for drift and performance

Signals:
1. ``system.billing.usage``: rows for Lakehouse Monitoring SKUs (MONITOR_*)
   or DLT-based monitoring pipelines in the last 30 days. Presence of any
   Lakehouse Monitoring DBU consumption is a strong proxy for active drift
   monitoring.

2. ``system.access.audit``: events for Databricks Lakehouse Monitoring API
   (createMonitor, getMonitor, runRefresh) that indicate monitoring tables
   have been configured for ML endpoints or feature tables.

Limitation: model performance monitoring can also be implemented via custom
jobs or external dashboards that are not visible in billing SKU names. Drift
monitoring requires ground-truth labels that are collected outside Databricks
and cannot be inferred from system tables. This check assesses whether the
monitoring *infrastructure* is provisioned, not whether model quality is
actually being tracked. A reviewer must confirm whether alert thresholds and label
collection pipelines are in place.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_MONITORING_BILLING_SQL = """\
SELECT sku_name,
       SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= current_date() - INTERVAL 30 DAYS
  AND (
    sku_name ILIKE '%MONITOR%'
    OR sku_name ILIKE '%LAKEHOUSE_MONITORING%'
    OR sku_name ILIKE '%INFERENCE_TABLE%'
  )
GROUP BY sku_name
ORDER BY total_dbus DESC\
"""

_MONITORING_AUDIT_SQL = """\
SELECT action_name,
       COUNT(*) AS event_count
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND (
    action_name ILIKE '%monitor%'
    OR action_name IN (
      'createMonitor', 'getMonitor', 'updateMonitor',
      'deleteMonitor', 'runRefresh', 'cancelRefresh'
    )
    OR service_name ILIKE '%monitor%'
  )
GROUP BY action_name
ORDER BY event_count DESC
LIMIT 10\
"""

_NOTE = (
    "Lakehouse Monitoring billing SKUs and audit events confirm that drift-monitoring "
    "infrastructure exists, but do not confirm that alert thresholds, label collection "
    "pipelines, or automated retraining triggers are wired. Custom monitoring jobs "
    "(e.g. bespoke Spark jobs comparing prediction distributions) do not appear in "
    "MONITOR SKU billing and are not detectable from system tables alone. A reviewer must confirm "
    "whether statistical drift tests (PSI, KS) and performance-degradation alerts are "
    "configured and reviewed regularly."
)

_REF = "https://docs.databricks.com/en/lakehouse-monitoring/index.html"


@register(layer="ml", question_ids=["ML-OE-05"])
class ModelMonitoringCheck(Check):
    """Assess model drift/performance monitoring via Lakehouse Monitoring signals.

    Evidence:
    - system.billing.usage: MONITOR/LAKEHOUSE_MONITORING SKU consumption.
    - system.access.audit: createMonitor / runRefresh API events.
    A note records that custom monitoring pipelines and alert configurations
    are not observable from system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        billing_rows = ctx.sql.query(_MONITORING_BILLING_SQL)
        audit_rows = ctx.sql.query(_MONITORING_AUDIT_SQL)

        total_dbus = sum(float(r.get("total_dbus") or 0) for r in billing_rows)

        if billing_rows:
            billing_summary = (
                f"{len(billing_rows)} Lakehouse Monitoring SKU(s) consumed "
                f"({round(total_dbus, 2)} total DBUs) in the last 30 days "
                "(system.billing.usage)"
            )
        else:
            billing_summary = (
                "No Lakehouse Monitoring SKU consumption found in "
                "system.billing.usage for the last 30 days"
            )

        billing_evidence = Evidence(
            kind="sql",
            summary=billing_summary,
            detail=_MONITORING_BILLING_SQL,
            rows=billing_rows,
            ref=_REF,
        )

        total_audit_events = sum(int(r.get("event_count") or 0) for r in audit_rows)

        if total_audit_events > 0:
            audit_summary = (
                f"{total_audit_events} Lakehouse Monitoring API event(s) "
                f"({len(audit_rows)} distinct action type(s)) in system.access.audit"
            )
        else:
            audit_summary = (
                "No Lakehouse Monitoring API events found in "
                "system.access.audit for the last 30 days"
            )

        audit_evidence = Evidence(
            kind="sql",
            summary=audit_summary,
            detail=_MONITORING_AUDIT_SQL,
            rows=audit_rows,
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [billing_evidence, audit_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
