"""Central catalog discoverability check (deterministic).

Answers:
  STO-IU-04  Use a central catalog for discovery of stored data

Signal: the share of managed/external tables registered in the Unity Catalog
central catalog (table_catalog <> 'hive_metastore') vs all managed/external
tables including those still in hive_metastore.  A table in hive_metastore is
not discoverable through the Unity Catalog central catalog, so the ratio
measures discoverability coverage directly.
Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.90
_PARTIAL_THRESHOLD = 0.60


@register(layer="storage", question_ids=["STO-IU-04"])
class CentralCatalogCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        sql = (
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN table_catalog <> 'hive_metastore' THEN 1 ELSE 0 END) AS governed "
            "FROM system.information_schema.tables "
            "WHERE table_type IN ('MANAGED','EXTERNAL')"
        )
        rows = ctx.sql.query(sql)
        row = rows[0] if rows else {"total": 0, "governed": 0}
        total = int(row.get("total") or 0)
        governed = int(row.get("governed") or 0)
        legacy = total - governed
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{governed} of {total} managed/external tables are discoverable via "
                    f"the Unity Catalog central catalog ({legacy} remain in hive_metastore)"
                ),
                detail=sql,
                rows=[{"total": total, "governed": governed, "legacy": legacy}],
                ref="https://docs.databricks.com/en/data-governance/unity-catalog/index.html",
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total"]
        governed = row["governed"]
        legacy = row["legacy"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No managed or external tables found in information_schema.tables "
                    "to evaluate central catalog discoverability."
                ),
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
                f"{governed} of {total} tables ({ratio:.0%}) are discoverable via the Unity "
                f"Catalog central catalog; {legacy} table(s) remain in hive_metastore and are "
                f"not centrally discoverable. Threshold for 'met' is {_MET_THRESHOLD:.0%}."
            ),
            sources=evidence,
        )
