"""Unity Catalog registration check (deterministic).

Answers:
  ING-DG-01  Register ingested data in Unity Catalog at the point of entry

Signal: the share of MANAGED/EXTERNAL tables governed by Unity Catalog vs the
legacy ``hive_metastore`` catalog, from ``system.information_schema.tables``.
Tables not in hive_metastore are treated as governed by UC.
Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.90
_PARTIAL_THRESHOLD = 0.60


@register(layer="ingestion", question_ids=["ING-DG-01"])
class UcRegistrationCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        sql = (
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN table_catalog = 'hive_metastore' THEN 1 ELSE 0 END) AS legacy "
            "FROM system.information_schema.tables "
            "WHERE table_type IN ('MANAGED','EXTERNAL')"
        )
        rows = ctx.sql.query(sql)
        row = rows[0] if rows else {"total": 0, "legacy": 0}
        total = int(row.get("total") or 0)
        legacy = int(row.get("legacy") or 0)
        governed = total - legacy
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{governed} of {total} tables are governed by Unity Catalog "
                    f"({legacy} remain in hive_metastore)"
                ),
                detail=sql,
                rows=[{"total": total, "legacy": legacy, "governed": governed}],
                ref="https://docs.databricks.com/en/data-governance/unity-catalog/index.html",
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total"]
        legacy = row["legacy"]
        governed = row["governed"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale="No tables found in information_schema.tables to evaluate UC coverage.",
                sources=evidence,
                auto_assessable=True,
            )

        ratio = governed / total
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
                f"{governed} of {total} tables ({ratio:.0%}) are registered in Unity Catalog; "
                f"{legacy} table(s) remain in hive_metastore. "
                f"Threshold for 'met' is {_MET_THRESHOLD:.0%}."
            ),
            sources=evidence,
        )
