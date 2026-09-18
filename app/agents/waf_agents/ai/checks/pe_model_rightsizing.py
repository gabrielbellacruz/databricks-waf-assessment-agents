"""Model right-sizing check (LLM-judged).

Answers:
  AI-PE-04  Right-size the model to the task

Evidence comes from two sources:
1. ``system.serving.endpoint_usage`` grouped by served entity: avg tokens per
   request per model — very low token usage on a large model is a
   cost-efficiency signal, while high token counts flag heavy usage.
2. ``system.billing.usage`` GPU SKUs: workspace-level GPU spend signals
   provisioned throughput (large model) adoption.

Right-sizing is inherently a task-model fit judgment (a small model may
suffice for classification but not for complex reasoning); this cannot be
determined from token counts and billing alone.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_TOKEN_SQL = """\
SELECT
  se.served_entity_name AS served_entity_name,
  COUNT(*) AS request_count,
  AVG(eu.input_token_count + eu.output_token_count) AS avg_tokens_per_request
FROM system.serving.endpoint_usage eu
JOIN system.serving.served_entities se
  ON eu.served_entity_id = se.served_entity_id
WHERE eu.request_time >= current_timestamp() - INTERVAL 30 DAYS
GROUP BY se.served_entity_name
ORDER BY avg_tokens_per_request DESC NULLS LAST\
"""

_GPU_SQL = """\
SELECT
  sku_name,
  SUM(usage_quantity) AS gpu_sku_dbus
FROM system.billing.usage
WHERE usage_date >= current_date() - INTERVAL 30 DAYS
  AND sku_name ILIKE '%GPU%'
GROUP BY sku_name
ORDER BY gpu_sku_dbus DESC\
"""

_NOTE = (
    "Model right-sizing requires matching task complexity to model capability: "
    "a small model (e.g., embedding or 7B) may suffice for classification or "
    "structured extraction, while complex reasoning needs a larger frontier model. "
    "Token counts and GPU spend are proxy signals — they indicate model usage "
    "patterns but cannot confirm appropriate task-model fit.  A reviewer must review "
    "the tasks each endpoint serves and assess whether a smaller or larger model "
    "would better balance cost, latency, and quality."
)

_REF = "https://docs.databricks.com/en/machine-learning/foundation-models/supported-models.html"


@register(layer="ai", question_ids=["AI-PE-04"])
class ModelRightsizingCheck(Check):
    """Assess model right-sizing via per-entity token usage and GPU billing.

    Evidence:
    1. system.serving.endpoint_usage (last 30 days) — avg tokens per request
       and latency per served entity.
    2. system.billing.usage — GPU SKU DBU spend by SKU name.
    A note records that task-model fit cannot be inferred from usage alone.
    LLM judges both.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        token_rows = ctx.sql.query(_TOKEN_SQL)
        gpu_rows = ctx.sql.query(_GPU_SQL)

        # Token evidence
        if not token_rows:
            token_summary = (
                "No serving endpoint requests found in system.serving.endpoint_usage "
                "for the last 30 days — no token-usage signal available"
            )
        else:
            entity_count = len(token_rows)
            max_tokens_row = token_rows[0]  # already ordered DESC
            max_entity = str(max_tokens_row.get("served_entity_name") or "")
            max_avg_tokens = round(float(max_tokens_row.get("avg_tokens_per_request") or 0), 1)
            token_summary = (
                f"{entity_count} served entity type(s) over last 30 days; "
                f"highest avg token use: '{max_entity}' at {max_avg_tokens} tokens/request"
            )

        # GPU billing evidence
        if not gpu_rows:
            gpu_summary = "No GPU billing SKUs found in system.billing.usage for the last 30 days"
        else:
            total_gpu = sum(float(r.get("gpu_sku_dbus") or 0) for r in gpu_rows)
            sku_names = [str(r.get("sku_name") or "") for r in gpu_rows[:5]]
            gpu_summary = (
                f"{total_gpu:.2f} GPU DBUs across {len(gpu_rows)} SKU(s) in last 30 days "
                f"(e.g. {', '.join(sku_names[:3])})"
            )

        return [
            Evidence(
                kind="sql",
                summary=token_summary,
                detail=_TOKEN_SQL,
                rows=token_rows[:10],
                ref=_REF,
            ),
            Evidence(
                kind="sql",
                summary=gpu_summary,
                detail=_GPU_SQL,
                rows=gpu_rows[:10],
                ref=_REF,
            ),
            Evidence(kind="note", summary=_NOTE, rows=[], ref=_REF),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
