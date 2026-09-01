"""Job-cluster compute check for orchestration (deterministic).

Answers:
  ORC-CO-01  Run workflows on job clusters

Signal: the share of workflow-triggered compute DBUs over the last 30 days
that are NOT on all-purpose clusters, from ``system.billing.usage`` filtered
to rows where ``usage_metadata.job_id IS NOT NULL``.  Job clusters and
serverless are the cost-efficient choice; all-purpose clusters carry a premium
DBU rate.  Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.90
_PARTIAL_THRESHOLD = 0.60
_WINDOW_DAYS = 30

_SQL = (
    "SELECT "
    "SUM(usage_quantity) AS total_dbus, "
    "SUM(CASE WHEN sku_name ILIKE '%ALL_PURPOSE%' THEN usage_quantity ELSE 0 END) "
    "AS all_purpose_dbus "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "AND sku_name ILIKE '%COMPUTE%' "
    "AND usage_metadata.job_id IS NOT NULL"
)

_REF = "https://docs.databricks.com/en/workflows/jobs/compute.html"


@register(layer="orchestration", question_ids=["ORC-CO-01"])
class OrcJobClustersCheck(Check):
    """Deterministic check for ORC-CO-01: workflow tasks on job clusters.

    Filters billing usage to workflow-triggered rows only (job_id IS NOT NULL)
    and measures what share of those DBUs are NOT on all-purpose clusters.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total_dbus": None, "all_purpose_dbus": None}
        total_dbus = float(row.get("total_dbus") or 0)
        all_purpose_dbus = float(row.get("all_purpose_dbus") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{all_purpose_dbus:.1f} of {total_dbus:.1f} workflow compute DBUs "
                    f"(last {_WINDOW_DAYS}d) are on all-purpose clusters"
                ),
                detail=_SQL,
                rows=[{"total_dbus": total_dbus, "all_purpose_dbus": all_purpose_dbus}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total_dbus = row["total_dbus"]
        all_purpose_dbus = row["all_purpose_dbus"]

        if total_dbus == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No workflow compute billing usage in the window; "
                    "cannot evaluate cluster-type distribution."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        compliant_dbus = total_dbus - all_purpose_dbus
        ratio = compliant_dbus / total_dbus
        if ratio >= _MET_THRESHOLD:
            verdict = Verdict.MET
        elif ratio >= _PARTIAL_THRESHOLD:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.NOT_MET

        all_purpose_share = all_purpose_dbus / total_dbus

        return Finding(
            question_id=question.id,
            pillar_id=question.pillar_id,
            verdict=verdict,
            confidence=Confidence.HIGH,
            score=round(ratio, 4),
            rationale=(
                f"{all_purpose_dbus:.1f} of {total_dbus:.1f} workflow compute DBUs "
                f"({all_purpose_share:.0%}) over the last {_WINDOW_DAYS} days are on "
                f"all-purpose clusters; {ratio:.0%} of workflow DBUs are on job or serverless "
                f"compute. Threshold for 'met' is {_MET_THRESHOLD:.0%} job/serverless."
            ),
            sources=evidence,
        )
