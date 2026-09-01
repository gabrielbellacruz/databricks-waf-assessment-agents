"""Table metadata / description coverage check (deterministic).

Answers:
  STO-DG-02  Manage metadata and descriptions for stored tables

Signal: the share of managed/external tables (outside hive_metastore) that
carry a non-empty ``comment`` field in ``system.information_schema.tables``.
Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.75
_PARTIAL_THRESHOLD = 0.40


@register(layer="storage", question_ids=["STO-DG-02"])
class TableMetadataCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        sql = (
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN comment IS NOT NULL AND trim(comment) <> '' THEN 1 ELSE 0 END) "
            "AS described "
            "FROM system.information_schema.tables "
            "WHERE table_type IN ('MANAGED','EXTERNAL') "
            "AND table_catalog <> 'hive_metastore'"
        )
        rows = ctx.sql.query(sql)
        row = rows[0] if rows else {"total": 0, "described": 0}
        total = int(row.get("total") or 0)
        described = int(row.get("described") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{described} of {total} managed/external tables have a non-empty description"
                ),
                detail=sql,
                rows=[{"total": total, "described": described}],
                ref=(
                    "https://docs.databricks.com/en/data-governance/unity-catalog/"
                    "best-practices.html"
                ),
            )
        ]

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
                    "No managed or external tables found in scope to evaluate metadata coverage."
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
                f"{described} of {total} tables ({ratio:.0%}) carry a non-empty description; "
                f"threshold for 'met' is {_MET_THRESHOLD:.0%}."
            ),
            sources=evidence,
        )
