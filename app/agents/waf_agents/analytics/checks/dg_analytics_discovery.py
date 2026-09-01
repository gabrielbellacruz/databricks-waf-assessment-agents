"""Analytics asset discovery coverage check (deterministic).

Answers:
  ANA-DG-05  Enable discovery of analytics assets

Signal: the share of managed/external tables (outside hive_metastore) that carry
a non-empty ``comment`` field in ``system.information_schema.tables``, plus the
count of tables with Unity Catalog tags from
``system.information_schema.table_tags``.  A non-empty description is the primary
discoverable signal that allows data consumers to find and evaluate assets via
Databricks Catalog Explorer or the Unity Catalog REST API.
Deterministic ratio (comment coverage) vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.75
_PARTIAL_THRESHOLD = 0.40

_DESCRIBED_SQL = (
    "SELECT COUNT(*) AS total,"
    " SUM(CASE WHEN comment IS NOT NULL AND trim(comment) <> '' THEN 1 ELSE 0 END)"
    " AS described"
    " FROM system.information_schema.tables"
    " WHERE table_type IN ('MANAGED','EXTERNAL')"
    " AND table_catalog <> 'hive_metastore'"
)

_TAGGED_SQL = (
    "SELECT COUNT(DISTINCT catalog_name || '.' || schema_name || '.' || table_name)"
    " AS tagged_tables"
    " FROM system.information_schema.table_tags"
    " WHERE catalog_name <> 'hive_metastore'"
)

_REF = (
    "https://docs.databricks.com/en/data-governance/unity-catalog/"
    "best-practices.html"
)


@register(layer="analytics", question_ids=["ANA-DG-05"])
class AnalyticsDiscoveryCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        desc_rows = ctx.sql.query(_DESCRIBED_SQL)
        tag_rows = ctx.sql.query(_TAGGED_SQL)

        drow = desc_rows[0] if desc_rows else {"total": 0, "described": 0}
        total = int(drow.get("total") or 0)
        described = int(drow.get("described") or 0)

        tagged_tables = int(
            (tag_rows[0].get("tagged_tables") or 0) if tag_rows else 0
        )

        description_evidence = Evidence(
            kind="sql",
            summary=(
                f"{described} of {total} managed/external UC tables have a non-empty description"
            ),
            detail=_DESCRIBED_SQL,
            rows=[{"total": total, "described": described}],
            ref=_REF,
        )
        tag_evidence = Evidence(
            kind="sql",
            summary=(
                f"{tagged_tables} UC table(s) carry at least one tag"
                " (supplementary discoverability signal)"
            ),
            detail=_TAGGED_SQL,
            rows=tag_rows[:5],
            ref=_REF,
        )
        return [description_evidence, tag_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total"]
        described = row["described"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No managed or external UC tables found; cannot evaluate analytics asset"
                    " discovery coverage."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = described / total
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
                f"{described} of {total} UC tables ({ratio:.0%}) carry a non-empty description"
                f" enabling discovery; threshold for 'met' is {_MET_THRESHOLD:.0%}."
            ),
            sources=evidence,
        )
