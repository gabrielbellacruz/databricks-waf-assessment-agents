"""Job-cluster compute check for ML training (deterministic).

Answers:
  ML-CO-02  Use job clusters for training runs

Signal: the share of GPU compute DBUs over the last 30 days that are NOT on
all-purpose clusters, from ``system.billing.usage`` filtered to GPU SKUs.
GPU training runs on job clusters (or serverless) avoid the all-purpose DBU
premium. Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.80
_PARTIAL_THRESHOLD = 0.40
_WINDOW_DAYS = 30

_SQL = (
    "SELECT "
    "SUM(usage_quantity) AS total_gpu_dbus, "
    "SUM(CASE WHEN sku_name ILIKE '%ALL_PURPOSE%' THEN usage_quantity ELSE 0 END) "
    "AS all_purpose_gpu_dbus "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "AND sku_name ILIKE '%GPU%'"
)

_REF = "https://docs.databricks.com/en/machine-learning/train-model/index.html"


@register(layer="ml", question_ids=["ML-CO-02"])
class MlJobClustersCheck(Check):
    """Deterministic check for ML-CO-02: training runs on job clusters.

    Filters billing usage to GPU SKUs and measures what share of those DBUs
    are NOT on all-purpose clusters. Job/serverless GPU clusters cost less per
    DBU than all-purpose GPU clusters and are automatically terminated after
    the run, eliminating idle GPU cost.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total_gpu_dbus": None, "all_purpose_gpu_dbus": None}
        total_gpu_dbus = float(row.get("total_gpu_dbus") or 0)
        all_purpose_gpu_dbus = float(row.get("all_purpose_gpu_dbus") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{all_purpose_gpu_dbus:.1f} of {total_gpu_dbus:.1f} GPU compute DBUs "
                    f"(last {_WINDOW_DAYS}d) are on all-purpose clusters"
                ),
                detail=_SQL,
                rows=[{
                    "total_gpu_dbus": total_gpu_dbus,
                    "all_purpose_gpu_dbus": all_purpose_gpu_dbus,
                }],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total_gpu_dbus = row["total_gpu_dbus"]
        all_purpose_gpu_dbus = row["all_purpose_gpu_dbus"]

        if total_gpu_dbus == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No GPU compute billing usage in the window; "
                    "cannot evaluate whether training runs use job clusters."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        compliant_dbus = total_gpu_dbus - all_purpose_gpu_dbus
        ratio = compliant_dbus / total_gpu_dbus
        if ratio >= _MET_THRESHOLD:
            verdict = Verdict.MET
        elif ratio >= _PARTIAL_THRESHOLD:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.NOT_MET

        all_purpose_share = all_purpose_gpu_dbus / total_gpu_dbus

        return Finding(
            question_id=question.id,
            pillar_id=question.pillar_id,
            verdict=verdict,
            confidence=Confidence.HIGH,
            score=round(ratio, 4),
            rationale=(
                f"{all_purpose_gpu_dbus:.1f} of {total_gpu_dbus:.1f} GPU compute DBUs "
                f"({all_purpose_share:.0%}) over the last {_WINDOW_DAYS} days are on "
                f"all-purpose clusters; {ratio:.0%} of GPU DBUs are on job or serverless "
                f"compute. Threshold for 'met' is {_MET_THRESHOLD:.0%} job/serverless."
            ),
            sources=evidence,
        )
