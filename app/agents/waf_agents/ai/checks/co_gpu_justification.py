"""GPU justification check (deterministic).

Answers:
  AI-CO-03  Only use GPUs where they are justified

Signal: system.billing.usage – GPU-tagged serving SKUs (sku_name ILIKE '%GPU%')
vs total serving SKUs over the last 30 days.  GPU DBU share of total serving DBUs
is a direct, high-confidence proxy for whether GPU compute dominates the AI
serving cost profile.

Thresholds (GPU share of serving DBUs):
  met      ≤ 30% — most serving is CPU-backed; cost-efficient default
  partial   31–70% — meaningful GPU spend; may or may not be justified
  not_met  > 70% — heavy GPU dependence; warrants manual review of every endpoint

The rationale notes explicitly that the billing ratio is a proxy: a high GPU
share is a signal, not a proof of waste — all endpoints might genuinely need GPUs.
Manual review is required to confirm justification.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 30
_MET_THRESHOLD = 0.30
_PARTIAL_THRESHOLD = 0.70

_SQL = (
    "SELECT "
    "SUM(usage_quantity) AS total_serving_dbu, "
    "SUM(CASE WHEN sku_name ILIKE '%GPU%' THEN usage_quantity ELSE 0 END) AS gpu_dbu "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "AND sku_name ILIKE '%SERVING%'"
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/index.html"


@register(layer="ai", question_ids=["AI-CO-03"])
class GpuJustificationCheck(Check):
    """Assess GPU-serving cost optimisation via billing SKU analysis.

    Computes GPU DBU share of total serving DBUs.  A high share is a cost-risk
    signal; whether any specific GPU endpoint is justified requires manual review.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total_serving_dbu": 0, "gpu_dbu": 0}
        total = float(row.get("total_serving_dbu") or 0)
        gpu = float(row.get("gpu_dbu") or 0)
        gpu_pct = round(100.0 * gpu / total, 1) if total > 0 else 0.0

        return [
            Evidence(
                kind="sql",
                summary=(
                    f"GPU serving: {gpu:.1f} of {total:.1f} total serving DBUs "
                    f"({gpu_pct}%) in the last {_WINDOW_DAYS} days"
                ),
                detail=_SQL,
                rows=[{"total_serving_dbu": total, "gpu_dbu": gpu, "gpu_pct": gpu_pct}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total_serving_dbu"]
        gpu = row["gpu_dbu"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No serving billing usage in the window — "
                    "cannot assess GPU utilisation."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = gpu / total
        if ratio <= _MET_THRESHOLD:
            verdict = Verdict.MET
        elif ratio <= _PARTIAL_THRESHOLD:
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
                f"GPU serving accounts for {gpu:.1f} of {total:.1f} serving DBUs "
                f"({ratio:.0%}) over the last {_WINDOW_DAYS} days. "
                f"Threshold for 'met' is ≤{_MET_THRESHOLD:.0%} GPU share. "
                "Whether specific GPU endpoints are justified requires manual review — "
                "the billing ratio is a proxy for overall GPU dependence."
            ),
            sources=evidence,
        )
