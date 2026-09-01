"""Compliance and content-safety requirements check (LLM-judged).

Answers:
  AI-SCP-04  Meet compliance and content-safety requirements

Signals:
1. ``system.ai_gateway.usage``: presence of guardrail activity (any blocked or
   PII-detected calls) confirms a content-safety layer is in use.
2. ``system.ai_gateway.usage``: share of calls that triggered guardrails —
   higher engagement suggests active safety policies.
3. ``system.billing.usage``: AI/serving-related SKU spend as context for scale
   (higher spend implies more exposure requiring compliance coverage).

Limitations noted:
- AI Gateway guardrails provide keyword/regex and safety classifiers but the
  specific content categories configured (violence, self-harm, hate speech,
  PII) are not exposed in usage rows.
- Regulatory compliance (HIPAA, GDPR, SOC 2) for AI output is not directly
  assessable from system tables.
- Custom application-level content filtering is not observable.
- Model cards, bias assessments, and responsible-AI documentation are not
  captured in system tables.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SAFETY_COVERAGE_SQL = """\
SELECT
  COUNT(*) AS total_calls,
  SUM(CASE WHEN guardrail_request_blocked = true
            OR guardrail_response_blocked = true
            OR guardrail_request_pii_detected = true
            OR guardrail_response_pii_detected = true
       THEN 1 ELSE 0 END) AS guardrail_active_calls,
  COUNT(DISTINCT endpoint_name) AS endpoints_with_guardrails
FROM system.ai_gateway.usage
WHERE timestamp >= current_timestamp() - INTERVAL 30 DAYS\
"""

_AI_SPEND_SQL = """\
SELECT
  sku_name,
  SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE (
    sku_name ILIKE '%SERVING%'
    OR sku_name ILIKE '%FOUNDATION_MODEL%'
    OR sku_name ILIKE '%INFERENCE%'
    OR sku_name ILIKE '%AI%'
  )
  AND usage_date >= current_date() - INTERVAL 30 DAYS
GROUP BY sku_name
ORDER BY total_dbus DESC
LIMIT 10\
"""

_NOTE = (
    "AI Gateway guardrail signals (PII detection, blocked calls) confirm that a safety "
    "layer is active for gateway-routed traffic, but the configuration of specific safety "
    "categories (violence, hate speech, self-harm, custom topics) is not exposed in "
    "system.ai_gateway.usage rows. Regulatory compliance posture for AI output "
    "(HIPAA, GDPR, SOC 2 controls around LLM use) requires policy documentation review "
    "and is not assessable from system tables. Model cards, bias evaluations, and "
    "responsible-AI governance artefacts are not captured in system tables. "
    "A reviewer must confirm that guardrail categories match compliance requirements and that "
    "a responsible-AI review process exists for deployed models."
)

_REF = "https://docs.databricks.com/en/ai-gateway/configure-ai-gateway.html#guardrails"


@register(layer="ai", question_ids=["AI-SCP-04"])
class ContentSafetyCheck(Check):
    """Assess compliance and content-safety coverage via AI Gateway guardrail signals.

    Evidence:
    - system.ai_gateway.usage: guardrail-active call count and endpoint coverage.
    - system.billing.usage: AI/serving SKU spend for exposure-scale context.
    A note records the limits of guardrail signals for full compliance assessment.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        safety_rows = ctx.sql.query(_SAFETY_COVERAGE_SQL)
        spend_rows = ctx.sql.query(_AI_SPEND_SQL)

        if safety_rows:
            s = safety_rows[0]
            total_calls = int(s.get("total_calls") or 0)
            guardrail_active = int(s.get("guardrail_active_calls") or 0)
            endpoints_covered = int(s.get("endpoints_with_guardrails") or 0)

            if total_calls > 0:
                guard_pct = round(100.0 * guardrail_active / total_calls, 1)
                safety_summary = (
                    f"AI Gateway: {total_calls} total calls; "
                    f"{guardrail_active} ({guard_pct}%) triggered a guardrail "
                    f"(blocked or PII detected); "
                    f"{endpoints_covered} endpoint(s) with guardrail activity "
                    "in the last 30 days"
                )
            else:
                safety_summary = (
                    "No AI Gateway calls in the last 30 days — "
                    "content-safety guardrail signals unavailable"
                )
        else:
            total_calls = guardrail_active = endpoints_covered = 0
            safety_summary = "No rows in system.ai_gateway.usage for the last 30 days"

        safety_evidence = Evidence(
            kind="sql",
            summary=safety_summary,
            detail=_SAFETY_COVERAGE_SQL,
            rows=[{
                "total_calls": total_calls,
                "guardrail_active_calls": guardrail_active,
                "endpoints_with_guardrails": endpoints_covered,
            }],
            ref=_REF,
        )

        total_ai_dbus = sum(float(r.get("total_dbus") or 0.0) for r in spend_rows)
        if spend_rows:
            spend_summary = (
                f"{len(spend_rows)} AI/serving SKU(s) consuming {total_ai_dbus:.1f} DBUs "
                "in the last 30 days — indicates scale of AI exposure requiring compliance"
            )
        else:
            spend_summary = (
                "No AI/serving billing SKUs found in the last 30 days — "
                "low AI exposure or usage not yet at scale"
            )

        spend_evidence = Evidence(
            kind="sql",
            summary=spend_summary,
            detail=_AI_SPEND_SQL,
            rows=spend_rows[:10],
            ref="https://docs.databricks.com/en/admin/system-tables/billing.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [safety_evidence, spend_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
