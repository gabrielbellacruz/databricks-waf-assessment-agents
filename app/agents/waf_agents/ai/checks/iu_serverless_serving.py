"""Serverless model serving adoption check (LLM-judged).

Answers:
  AI-IU-05  Use serverless model serving

Signal:
  1. system.billing.usage — Model Serving SKUs; presence of 'SERVERLESS' in the
     SKU name or Foundation Model API SKUs (which are inherently serverless) are
     strong indicators. Provisioned throughput SKUs ('PROVISIONED_THROUGHPUT')
     indicate dedicated (non-serverless) endpoints.
  2. system.ai_gateway.usage — calls routed through AI Gateway to Foundation
     Model API endpoints (serverless by nature).

Limitation note: The split between serverless and provisioned-throughput
endpoints is not always cleanly inferrable from billing SKU names alone. Serving
endpoint type (serverless, provisioned throughput, GPU cluster-based) requires
review via the Serving Endpoints REST API. Billing rows for model serving may be
absent if the feature is unused or if SKU naming differs by workspace tier.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_BILLING_SQL = (
    "SELECT"
    " SUM(CASE WHEN LOWER(sku_name) LIKE '%serverless%'"
    "           AND LOWER(sku_name) LIKE '%model%' THEN usage_quantity ELSE 0 END)"
    "  AS serverless_serving_dbus,"
    " SUM(CASE WHEN LOWER(sku_name) LIKE '%provisioned_throughput%'"
    "           OR LOWER(sku_name) LIKE '%provisioned%model%' THEN usage_quantity ELSE 0 END)"
    "  AS provisioned_serving_dbus,"
    " SUM(CASE WHEN LOWER(sku_name) LIKE '%foundation_model%'"
    "           OR LOWER(sku_name) LIKE '%fmapi%' THEN usage_quantity ELSE 0 END)"
    "  AS fmapi_serving_dbus"
    " FROM system.billing.usage"
    " WHERE LOWER(sku_name) LIKE '%model%serving%'"
    "    OR LOWER(sku_name) LIKE '%serving%model%'"
    "    OR LOWER(sku_name) LIKE '%foundation_model%'"
    "    OR LOWER(sku_name) LIKE '%fmapi%'"
    "    OR LOWER(sku_name) LIKE '%external_model%'"
)

_GATEWAY_SQL = (
    "SELECT COUNT(*) AS fmapi_gateway_calls,"
    " COUNT(DISTINCT endpoint_name) AS fmapi_gateway_endpoints"
    " FROM system.ai_gateway.usage"
    " WHERE CAST(window_start_time AS DATE) >= CURRENT_DATE - INTERVAL 30 DAYS"
)

_REF = (
    "https://docs.databricks.com/en/machine-learning/model-serving/serverless-model-serving.html"
)

_SERVERLESS_LIMITATION = (
    "The distinction between serverless and provisioned-throughput model serving"
    " is not always inferrable from billing SKU names alone; SKU naming varies by"
    " workspace tier and region. Foundation Model API calls (system.ai_gateway.usage)"
    " are serverless by definition. Provisioned throughput endpoints require review"
    " via GET /api/2.0/serving-endpoints."
)


@register(layer="ai", question_ids=["AI-IU-05"])
class AiServerlessServingCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        billing_rows = ctx.sql.query(_BILLING_SQL)
        gateway_rows = ctx.sql.query(_GATEWAY_SQL)

        b = billing_rows[0] if billing_rows else {}
        serverless_dbus = float(b.get("serverless_serving_dbus") or 0.0)
        provisioned_dbus = float(b.get("provisioned_serving_dbus") or 0.0)
        fmapi_dbus = float(b.get("fmapi_serving_dbus") or 0.0)

        g = gateway_rows[0] if gateway_rows else {}
        fmapi_calls = int(g.get("fmapi_gateway_calls") or 0)
        fmapi_endpoints = int(g.get("fmapi_gateway_endpoints") or 0)

        billing_evidence = Evidence(
            kind="sql",
            summary=(
                f"Model serving DBUs — serverless: {serverless_dbus:.2f},"
                f" provisioned: {provisioned_dbus:.2f},"
                f" FMAPI (serverless): {fmapi_dbus:.2f}"
            ),
            detail=_BILLING_SQL,
            rows=[{
                "serverless_serving_dbus": serverless_dbus,
                "provisioned_serving_dbus": provisioned_dbus,
                "fmapi_serving_dbus": fmapi_dbus,
            }],
            ref=_REF,
        )
        gateway_evidence = Evidence(
            kind="sql",
            summary=(
                f"{fmapi_calls} AI Gateway call(s) to {fmapi_endpoints} endpoint(s)"
                " in the last 30 days (Foundation Model API = serverless)"
            ),
            detail=_GATEWAY_SQL,
            rows=[{
                "fmapi_gateway_calls": fmapi_calls,
                "fmapi_gateway_endpoints": fmapi_endpoints,
            }],
            ref=_REF,
        )
        limitation = Evidence(
            kind="uc_metadata",
            summary=_SERVERLESS_LIMITATION,
            detail=(
                "List serving endpoints via GET /api/2.0/serving-endpoints and check"
                " the 'config.served_entities[].workload_size' field; absence or"
                " 'Automatic' implies serverless auto-scaling."
            ),
            ref=_REF,
        )
        return [billing_evidence, gateway_evidence, limitation]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
