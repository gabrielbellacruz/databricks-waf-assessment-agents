"""ML cost-attribution tagging check (deterministic).

Answers:
  ML-CO-05  Attribute ML training and serving cost

Signal: the share of ML-specific billing usage records that carry at least one
custom tag, from ``system.billing.usage`` filtered to GPU compute and model-
serving SKUs.  Tagged usage allows ML training and inference cost to be
attributed to a model, experiment, team, or project in cost-analysis dashboards.
Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.80
_PARTIAL_THRESHOLD = 0.40
_WINDOW_DAYS = 30

_SQL = (
    "SELECT COUNT(*) AS total, "
    "SUM(CASE WHEN custom_tags IS NOT NULL AND size(custom_tags) > 0 "
    "THEN 1 ELSE 0 END) AS tagged "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "AND (sku_name ILIKE '%GPU%' OR sku_name ILIKE '%MODEL_SERVING%' "
    "OR sku_name ILIKE '%SERVING%' OR sku_name ILIKE '%MACHINE_LEARN%')"
)

_REF = "https://docs.databricks.com/en/admin/account-settings/usage-detail-tags.html"


@register(layer="ml", question_ids=["ML-CO-05"])
class MlCostTaggingCheck(Check):
    """Deterministic check for ML-CO-05: custom tags on ML billing records.

    Mirrors the pattern from the ingestion and analytics cost-attribution checks
    but filters to ML-specific SKUs (GPU compute and model-serving). A billing
    record that lacks custom tags cannot be attributed to a model, team, or
    experiment in showback/chargeback reports.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total": 0, "tagged": 0}
        total = int(row.get("total") or 0)
        tagged = int(row.get("tagged") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{tagged} of {total} ML billing usage records "
                    f"(last {_WINDOW_DAYS}d) carry a custom tag"
                ),
                detail=_SQL,
                rows=[{"total": total, "tagged": tagged}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total, tagged = row["total"], row["tagged"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No ML billing usage (GPU or model-serving SKUs) in the window "
                    "to evaluate cost-attribution tag coverage."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = tagged / total
        if ratio >= _MET_THRESHOLD:
            verdict = Verdict.MET
        elif ratio >= _PARTIAL_THRESHOLD:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.NOT_MET

        return Finding(
            question_id=question.id,
            pillar_id=question.pillar_id,
            verdict=verdict,
            confidence=Confidence.HIGH,
            score=round(ratio, 4),
            rationale=(
                f"{tagged} of {total} ML billing usage records ({ratio:.0%}) over the "
                f"last {_WINDOW_DAYS} days carry a custom tag; threshold for 'met' is "
                f"{_MET_THRESHOLD:.0%}. Untagged ML usage cannot be attributed to a "
                "model, experiment, or team in cost-analysis reports."
            ),
            sources=evidence,
        )
