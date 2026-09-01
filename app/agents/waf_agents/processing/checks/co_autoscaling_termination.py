"""Autoscaling and auto-termination check for the processing layer (deterministic).

Answers:
  PRO-CO-03  Use autoscaling and auto-termination for processing

Signal: two ratios from system.compute.clusters:
  1. Fraction of active clusters with autoscaling enabled
     (max_autoscale_workers > min_autoscale_workers).
  2. Fraction of interactive (UI/API) clusters with auto-termination configured
     (auto_termination_minutes > 0).
The combined verdict thresholds on the lower of the two ratios — both
practices need to be adopted for the workspace to be considered compliant.
Deterministic -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.80
_PARTIAL_THRESHOLD = 0.40

_AUTOSCALING_SQL = (
    "SELECT COUNT(*) AS total, "
    "SUM(CASE WHEN max_autoscale_workers > min_autoscale_workers THEN 1 ELSE 0 END) AS autoscaling "
    "FROM system.compute.clusters "
    "WHERE delete_time IS NULL"
)

_AUTOTERMINATION_SQL = (
    "SELECT COUNT(*) AS total, "
    "SUM(CASE WHEN auto_termination_minutes > 0 THEN 1 ELSE 0 END) AS auto_term "
    "FROM system.compute.clusters "
    "WHERE cluster_source IN ('UI','API') AND delete_time IS NULL"
)


@register(layer="processing", question_ids=["PRO-CO-03"])
class ProcessingAutoscalingTerminationCheck(Check):
    """Check that processing clusters use autoscaling and auto-termination.

    Two signals: autoscaling ratio (all active clusters) and auto-termination
    ratio (interactive clusters only). Job clusters are ephemeral and excluded
    from the auto-termination denominator. The verdict is thresholded on the
    lower of the two ratios so both practices need to be adopted.
    Note: covers all workspace clusters, not processing pipelines specifically.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        as_rows = ctx.sql.query(_AUTOSCALING_SQL)
        as_row = as_rows[0] if as_rows else {"total": 0, "autoscaling": 0}
        as_total = int(as_row.get("total") or 0)
        as_count = int(as_row.get("autoscaling") or 0)

        at_rows = ctx.sql.query(_AUTOTERMINATION_SQL)
        at_row = at_rows[0] if at_rows else {"total": 0, "auto_term": 0}
        at_total = int(at_row.get("total") or 0)
        at_count = int(at_row.get("auto_term") or 0)

        autoscaling_ev = Evidence(
            kind="sql",
            summary=f"{as_count} of {as_total} active clusters have autoscaling enabled",
            detail=_AUTOSCALING_SQL,
            rows=[{"total": as_total, "autoscaling": as_count}],
            ref="https://docs.databricks.com/en/compute/configure.html#autoscaling",
        )
        autotermination_ev = Evidence(
            kind="sql",
            summary=f"{at_count} of {at_total} interactive clusters have auto-termination set",
            detail=_AUTOTERMINATION_SQL,
            rows=[{"total": at_total, "auto_term": at_count}],
            ref="https://docs.databricks.com/en/compute/cluster-config-best-practices.html",
        )
        return [autoscaling_ev, autotermination_ev]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        as_row = evidence[0].rows[0]
        at_row = evidence[1].rows[0]

        as_total = as_row["total"]
        as_count = as_row["autoscaling"]
        at_total = at_row["total"]
        at_count = at_row["auto_term"]

        if as_total == 0 and at_total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No active clusters found in system.compute.clusters; "
                    "cannot evaluate autoscaling or auto-termination coverage."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        as_ratio = as_count / as_total if as_total > 0 else 0.0
        at_ratio = at_count / at_total if at_total > 0 else 0.0
        # Verdict on the worse of the two signals
        ratio = min(as_ratio, at_ratio)

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
                f"Autoscaling: {as_count}/{as_total} active clusters ({as_ratio:.0%}); "
                f"auto-termination: {at_count}/{at_total} interactive clusters ({at_ratio:.0%}). "
                f"Combined score (lower of the two) is {ratio:.0%}; "
                f"threshold for 'met' is {_MET_THRESHOLD:.0%}. "
                "Note: this signal covers all workspace clusters, not processing jobs specifically."
            ),
            sources=evidence,
        )
