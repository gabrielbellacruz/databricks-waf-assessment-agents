"""Multi-LLM provider management check (LLM-judged).

Answers:
  AI-IU-02  Streamline management of multiple LLM providers

Signal:
  1. system.ai_gateway.usage — distinct endpoint_names routed through the AI
     Gateway; multiple endpoints suggests multi-provider management. Rows present
     confirm AI Gateway is being used (the recommended centralisation layer).
  2. system.billing.usage — External Model SKUs (pay-per-token third-party models
     such as OpenAI, Anthropic, Cohere) alongside Foundation Model API SKUs
     indicate use of multiple providers through a single management plane.

Limitation note: Which endpoints serve which underlying provider (OpenAI,
Anthropic, Meta Llama, etc.) is not exposed through system tables. Provider
classification requires reviewing serving endpoint configurations via the
Serving Endpoints REST API.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_GATEWAY_SQL = (
    "SELECT COUNT(DISTINCT endpoint_name) AS distinct_llm_providers,"
    " COUNT(*) AS total_gateway_calls"
    " FROM system.ai_gateway.usage"
    " WHERE CAST(window_start_time AS DATE) >= CURRENT_DATE - INTERVAL 30 DAYS"
)

_BILLING_SQL = (
    "SELECT"
    " SUM(CASE WHEN LOWER(sku_name) LIKE '%external_model%' THEN usage_quantity ELSE 0 END)"
    "  AS ext_model_dbus,"
    " SUM(CASE WHEN LOWER(sku_name) LIKE '%foundation_model%'"
    "           OR LOWER(sku_name) LIKE '%fmapi%' THEN usage_quantity ELSE 0 END)"
    "  AS internal_model_dbus"
    " FROM system.billing.usage"
    " WHERE (LOWER(sku_name) LIKE '%external_model%'"
    "     OR LOWER(sku_name) LIKE '%foundation_model%'"
    "     OR LOWER(sku_name) LIKE '%fmapi%')"
)

_REF = "https://docs.databricks.com/en/generative-ai/external-models/index.html"

_PROVIDER_LIMITATION = (
    "The underlying LLM provider (OpenAI, Anthropic, Cohere, Meta, Mistral, etc.)"
    " of each serving endpoint is not exposed in system.ai_gateway.usage or"
    " system.billing.usage. Review serving endpoint configurations via"
    " GET /api/2.0/serving-endpoints to classify providers."
)


@register(layer="ai", question_ids=["AI-IU-02"])
class AiLlmProvidersCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        gateway_rows = ctx.sql.query(_GATEWAY_SQL)
        billing_rows = ctx.sql.query(_BILLING_SQL)

        g = gateway_rows[0] if gateway_rows else {}
        distinct_endpoints = int(g.get("distinct_llm_providers") or 0)
        total_calls = int(g.get("total_gateway_calls") or 0)

        b = billing_rows[0] if billing_rows else {}
        ext_dbus = float(b.get("ext_model_dbus") or 0.0)
        int_dbus = float(b.get("internal_model_dbus") or 0.0)

        gateway_evidence = Evidence(
            kind="sql",
            summary=(
                f"{distinct_endpoints} distinct LLM endpoint(s) routed through"
                f" AI Gateway with {total_calls} call(s) in the last 30 days"
            ),
            detail=_GATEWAY_SQL,
            rows=[{
                "distinct_llm_providers": distinct_endpoints,
                "total_gateway_calls": total_calls,
            }],
            ref=_REF,
        )
        billing_evidence = Evidence(
            kind="sql",
            summary=(
                f"External model DBUs: {ext_dbus:.2f};"
                f" Foundation Model API DBUs: {int_dbus:.2f}"
                " (mixing external + internal = multi-provider)"
            ),
            detail=_BILLING_SQL,
            rows=[{"ext_model_dbus": ext_dbus, "internal_model_dbus": int_dbus}],
            ref=_REF,
        )
        limitation = Evidence(
            kind="uc_metadata",
            summary=_PROVIDER_LIMITATION,
            detail=(
                "Confirm multi-provider strategy by reviewing serving endpoint configs"
                " and AI Gateway route definitions in the Databricks UI."
            ),
            ref=_REF,
        )
        return [gateway_evidence, billing_evidence, limitation]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
