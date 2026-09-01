"""Job-cluster compute check.

Answers:
  ING-CO-01  Use job clusters for scheduled ingestion

Signal: the share of compute DBUs over the last 30 days that are NOT on
all-purpose clusters.  Job clusters and serverless are the cost-efficient
choice for scheduled work; all-purpose clusters carry a premium DBU rate.
Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.90
_PARTIAL_THRESHOLD = 0.60
_WINDOW_DAYS = 30


@register(layer="ingestion", question_ids=["ING-CO-01"])
class JobComputeCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        sql = (
            "SELECT "
            "SUM(usage_quantity) AS total_dbus, "
            "SUM(CASE WHEN sku_name ILIKE '%ALL_PURPOSE%' THEN usage_quantity ELSE 0 END) "
            "AS all_purpose_dbus "
            "FROM system.billing.usage "
            f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
            "AND sku_name ILIKE '%COMPUTE%'"
        )
        rows = ctx.sql.query(sql)
        row = rows[0] if rows else {"total_dbus": None, "all_purpose_dbus": None}
        total_dbus = float(row.get("total_dbus") or 0)
        all_purpose_dbus = float(row.get("all_purpose_dbus") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{all_purpose_dbus:.1f} of {total_dbus:.1f} compute DBUs "
                    f"(last {_WINDOW_DAYS}d) are on all-purpose clusters"
                ),
                detail=sql,
                rows=[{"total_dbus": total_dbus, "all_purpose_dbus": all_purpose_dbus}],
                ref="https://docs.databricks.com/en/compute/cluster-config-best-practices.html",
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
                    "No compute billing usage in the window to evaluate cluster type distribution."
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
                f"{all_purpose_dbus:.1f} of {total_dbus:.1f} compute DBUs "
                f"({all_purpose_share:.0%}) over the last {_WINDOW_DAYS} days are on "
                f"all-purpose clusters; {ratio:.0%} of DBUs are on job or serverless compute. "
                f"Threshold for 'met' is {_MET_THRESHOLD:.0%} job/serverless."
            ),
            sources=evidence,
        )
