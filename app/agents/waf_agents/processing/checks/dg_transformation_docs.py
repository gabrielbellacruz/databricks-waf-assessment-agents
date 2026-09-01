"""Transformation documentation coverage check (deterministic).

Answers:
  PRO-DG-03  Document transformation logic and business rules

Signal: the share of managed/external Unity Catalog tables that carry a
non-empty table comment (description), from
``system.information_schema.tables``.  Table comments are the primary
platform-observable proxy for documented transformation logic and business
rules: a well-documented estate typically has descriptions on its tables.
MEDIUM confidence: a comment may be a brief label rather than a full
business-rule description, and column-level documentation is not captured.
Denominator 0 -> UNKNOWN/LOW.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.50
_PARTIAL_THRESHOLD = 0.20

_SQL = (
    "SELECT COUNT(*) AS total, "
    "SUM(CASE WHEN comment IS NOT NULL AND comment <> '' THEN 1 ELSE 0 END) AS documented "
    "FROM system.information_schema.tables "
    "WHERE table_type IN ('MANAGED', 'EXTERNAL') "
    "AND table_catalog <> 'hive_metastore'"
)

_REF = "https://docs.databricks.com/en/data-governance/unity-catalog/manage-table-metadata.html"


@register(layer="processing", question_ids=["PRO-DG-03"])
class ProcessingTransformationDocsCheck(Check):
    """Assess transformation documentation via Unity Catalog table comment coverage.

    Queries ``system.information_schema.tables`` for the ratio of
    managed/external UC tables that carry a non-empty ``comment``.  High
    comment coverage indicates the team documents the purpose of their tables
    (a proxy for transformation logic and business-rule documentation).
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total": 0, "documented": 0}
        total = int(row.get("total") or 0)
        documented = int(row.get("documented") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{documented} of {total} managed/external UC tables "
                    "have a non-empty table comment (description)"
                ),
                detail=_SQL,
                rows=[{"total": total, "documented": documented}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total"]
        documented = row["documented"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No managed or external tables found outside hive_metastore; "
                    "cannot assess documentation coverage."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = documented / total
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
            confidence=Confidence.MEDIUM,
            score=round(ratio, 4),
            rationale=(
                f"{documented} of {total} managed/external UC tables ({ratio:.0%}) "
                f"carry a non-empty table comment; threshold for 'met' is {_MET_THRESHOLD:.0%}. "
                "Confidence is MEDIUM: table comments are a proxy for transformation "
                "documentation — a terse label satisfies the check, so manual review of comment "
                "quality is recommended."
            ),
            sources=evidence,
        )
