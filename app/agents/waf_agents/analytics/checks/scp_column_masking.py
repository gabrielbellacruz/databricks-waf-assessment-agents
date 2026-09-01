"""Column-masking coverage check (deterministic).

Answers:
  ANA-SCP-03  Mask sensitive fields in analytics outputs

Signal: share of non-hive_metastore columns that have a Unity Catalog column
masking policy applied, derived from two queries:
  1. system.information_schema.column_masks  -> masked column count (numerator)
  2. system.information_schema.columns       -> total column count (denominator)

A masking-policy ratio close to zero is expected for most workspaces;
thresholds are set conservatively: met >= 0.10 (10%), partial >= 0.02 (2%).
Denominator 0 (no columns outside hive_metastore) -> UNKNOWN/LOW.
Deterministic ratio -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MASKED_SQL = (
    "SELECT COUNT(*) AS masked_columns "
    "FROM system.information_schema.column_masks "
    "WHERE table_catalog <> 'hive_metastore'"
)

_TOTAL_SQL = (
    "SELECT COUNT(*) AS total_columns "
    "FROM system.information_schema.columns "
    "WHERE table_catalog <> 'hive_metastore'"
)

_MET_THRESHOLD = 0.10   # >=10% of columns masked -> met
_PARTIAL_THRESHOLD = 0.02  # >=2% -> partial

_MASK_REF = (
    "https://docs.databricks.com/en/data-governance/unity-catalog/row-and-column-filters.html"
)


@register(layer="analytics", question_ids=["ANA-SCP-03"])
class ColumnMaskingCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        masked_rows = ctx.sql.query(_MASKED_SQL)
        masked = int(
            (masked_rows[0].get("masked_columns") if masked_rows else None) or 0
        )

        total_rows = ctx.sql.query(_TOTAL_SQL)
        total = int(
            (total_rows[0].get("total_columns") if total_rows else None) or 0
        )

        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{masked} column(s) have a masking policy applied "
                    f"(outside hive_metastore)"
                ),
                detail=_MASKED_SQL,
                rows=[{"masked_columns": masked}],
                ref=_MASK_REF,
            ),
            Evidence(
                kind="sql",
                summary=(
                    f"{total} total columns found outside hive_metastore (denominator)"
                ),
                detail=_TOTAL_SQL,
                rows=[{"total_columns": total}],
                ref=_MASK_REF,
            ),
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        masked = evidence[0].rows[0]["masked_columns"]
        total = evidence[1].rows[0]["total_columns"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No columns found outside hive_metastore; "
                    "cannot assess column-masking coverage."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = min(1.0, masked / total)
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
                f"{masked} of {total} columns ({ratio:.2%}) have a masking policy; "
                f"threshold for 'met' is ≥{_MET_THRESHOLD:.0%} of all columns."
            ),
            sources=evidence,
        )
