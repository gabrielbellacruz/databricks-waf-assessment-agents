"""Cost-attribution tagging check (deterministic exemplar).

Answers:
  ING-CO-04  Tag and attribute ingestion costs

Signal: the share of recent billing usage records that carry any custom tag,
from ``system.billing.usage``. Tagged usage is what makes cost attributable to a
source or team. Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.80
_PARTIAL_THRESHOLD = 0.40
_WINDOW_DAYS = 30


@register(layer="ingestion", question_ids=["ING-CO-04"])
class CostTaggingCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        sql = (
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN custom_tags IS NOT NULL AND size(custom_tags) > 0 "
            "THEN 1 ELSE 0 END) AS tagged "
            "FROM system.billing.usage "
            f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS"
        )
        rows = ctx.sql.query(sql)
        row = rows[0] if rows else {"total": 0, "tagged": 0}
        total = int(row.get("total") or 0)
        tagged = int(row.get("tagged") or 0)
        return [
            Evidence(
                kind="sql",
                summary=f"{tagged} of {total} billing usage records "
                f"(last {_WINDOW_DAYS}d) carry a custom tag",
                detail=sql,
                rows=[{"total": total, "tagged": tagged}],
                ref="https://docs.databricks.com/en/admin/account-settings/usage-detail-tags.html",
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
                rationale="No billing usage in the window to evaluate tag coverage.",
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
                f"{tagged} of {total} billing usage records ({ratio:.0%}) over the last "
                f"{_WINDOW_DAYS} days carry a custom tag; threshold for 'met' is "
                f"{_MET_THRESHOLD:.0%}. Untagged usage cannot be attributed to a source or team."
            ),
            sources=evidence,
        )
