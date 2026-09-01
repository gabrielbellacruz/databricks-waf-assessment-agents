"""Self-service ML development environments check (LLM-judged).

Answers:
  ML-IU-03  Provide self-service ML development environments

Signals:
  * ``system.billing.usage`` — count of billing records and distinct workspaces that
    consumed ML-related SKUs (JOBS_COMPUTE, ALL_PURPOSE_COMPUTE, MODEL_SERVING) in the
    last 90 days. Broad ML compute usage across the workspace is a proxy for self-service
    access.
  * ``system.billing.usage`` — distinct count of billing records with ML-related SKUs
    broken down by custom-tag presence. Tagged usage suggests team-owned, self-service
    environments rather than centralised runs.
  * Note: whether compute access is genuinely self-service (vs bottlenecked through a
    central team) is not directly observable from billing alone. Cluster policies, Databricks
    Apps, and workspace configuration (enabled runtimes, shared clusters) are stronger
    signals but are not in system tables.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 90

# ML compute SKU usage in the window.
_ML_USAGE_SQL = (
    "SELECT COUNT(*) AS ml_usage_rows, "
    "COUNT(DISTINCT workspace_id) AS workspaces_using_ml, "
    "SUM(CASE WHEN custom_tags IS NOT NULL AND size(custom_tags) > 0 THEN 1 ELSE 0 END) "
    "  AS tagged_ml_rows "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "  AND (sku_name ILIKE '%ML%' "
    "       OR sku_name ILIKE '%ALL_PURPOSE%' "
    "       OR sku_name ILIKE '%MODEL_SERVING%')"
)

# SKU distribution for ML compute in the window.
_ML_SKU_DISTRIBUTION_SQL = (
    "SELECT sku_name AS ml_sku_name, COUNT(*) AS sku_rows "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "  AND (sku_name ILIKE '%ML%' "
    "       OR sku_name ILIKE '%MODEL_SERVING%') "
    "GROUP BY sku_name "
    "ORDER BY sku_rows DESC "
    "LIMIT 10"
)

_NOTE = (
    "Self-service ML development readiness is not fully observable from billing. "
    "Key signals that are NOT in system tables include: cluster policy enablement, "
    "Databricks Apps availability, allowed runtime versions, and whether individual "
    "engineers can create their own clusters. Billing breadth (many workspaces, tagged "
    "usage) is used as an indirect proxy — manual confirmation recommended."
)

_REF = "https://docs.databricks.com/en/machine-learning/index.html"


@register(layer="ml", question_ids=["ML-IU-03"])
class MlEnvironmentsCheck(Check):
    """LLM-judged check for ML-IU-03: self-service ML development environments."""

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        usage_rows = ctx.sql.query(_ML_USAGE_SQL)
        sku_rows = ctx.sql.query(_ML_SKU_DISTRIBUTION_SQL)

        urow = usage_rows[0] if usage_rows else {}
        ml_usage_rows = int(urow.get("ml_usage_rows") or 0)
        workspaces_using_ml = int(urow.get("workspaces_using_ml") or 0)
        tagged_ml_rows = int(urow.get("tagged_ml_rows") or 0)

        usage_evidence = Evidence(
            kind="sql",
            summary=(
                f"{ml_usage_rows} ML-related billing records in the last {_WINDOW_DAYS} days "
                f"across {workspaces_using_ml} workspace(s); "
                f"{tagged_ml_rows} records carry a custom tag"
            ),
            detail=_ML_USAGE_SQL,
            rows=[
                {
                    "ml_usage_rows": ml_usage_rows,
                    "workspaces_using_ml": workspaces_using_ml,
                    "tagged_ml_rows": tagged_ml_rows,
                }
            ],
            ref=_REF,
        )
        sku_evidence = Evidence(
            kind="sql",
            summary=(
                f"{len(sku_rows)} distinct ML-related SKU type(s) consumed "
                f"(top-10 by usage rows shown)"
            ),
            detail=_ML_SKU_DISTRIBUTION_SQL,
            rows=sku_rows[:10],
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )
        return [usage_evidence, sku_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
