"""Lineage coverage check.

Answers:
  ING-DG-02  Capture lineage from source systems into the lakehouse

Signal: the share of governed tables (MANAGED/EXTERNAL in Unity Catalog) that appear
as a lineage target in ``system.access.table_lineage`` within the last 90 days.
Lineage presence is a proxy for having captured lineage from source systems: it
confirms events were recorded but does not distinguish whether the upstream sources
are truly external. MEDIUM confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.60
_PARTIAL_THRESHOLD = 0.30
_WINDOW_DAYS = 90


@register(layer="ingestion", question_ids=["ING-DG-02"])
class LineageCoverageCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        sql = (
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN t.full_name IN ("
            "SELECT DISTINCT target_table_full_name FROM system.access.table_lineage "
            f"WHERE event_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS"
            ") THEN 1 ELSE 0 END) AS with_lineage "
            "FROM ("
            "SELECT table_catalog || '.' || table_schema || '.' || table_name AS full_name "
            "FROM system.information_schema.tables "
            "WHERE table_type IN ('MANAGED', 'EXTERNAL') AND table_catalog <> 'hive_metastore'"
            ") t"
        )
        rows = ctx.sql.query(sql)
        row = rows[0] if rows else {"total": 0, "with_lineage": 0}
        total = int(row.get("total") or 0)
        with_lineage = int(row.get("with_lineage") or 0)
        return [
            Evidence(
                kind="sql",
                summary=f"{with_lineage} of {total} governed tables have lineage recorded "
                f"in the last {_WINDOW_DAYS} days",
                detail=sql,
                rows=[{"total": total, "with_lineage": with_lineage}],
                ref=(
                    "https://docs.databricks.com/en/data-governance/"
                    "unity-catalog/data-lineage.html"
                ),
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total, with_lineage = row["total"], row["with_lineage"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale="No governed tables found in Unity Catalog to evaluate lineage coverage.",
                sources=evidence,
                auto_assessable=True,
            )

        ratio = with_lineage / total
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
                f"{with_lineage} of {total} governed tables ({ratio:.0%}) appear as a lineage "
                f"target in system.access.table_lineage in the last {_WINDOW_DAYS} days; "
                f"threshold for 'met' is {_MET_THRESHOLD:.0%}. "
                "Lineage presence is a proxy for captured lineage from source systems: it "
                "confirms events were recorded but does not verify the ultimate source origin."
            ),
            sources=evidence,
        )
