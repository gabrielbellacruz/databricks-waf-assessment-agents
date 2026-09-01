"""Lineage coverage through transformation pipelines (deterministic).

Answers:
  PRO-DG-01  Capture lineage through transformation pipelines

Signal: the share of governed Unity Catalog tables that appear as a lineage
target with a known upstream source table in ``system.access.table_lineage``
within the last 90 days.  A non-null ``source_table_full_name`` indicates
table-to-table lineage was recorded — confirming that a transformation pipeline
wrote to the target and Unity Catalog captured the upstream dependency.
MEDIUM confidence: lineage captures what UC observed; Python/Spark tasks
without a SQL lineage surface may not be fully reflected.
Denominator 0 -> UNKNOWN/LOW.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.60
_PARTIAL_THRESHOLD = 0.30
_WINDOW_DAYS = 90

_SQL_TOTAL = (
    "SELECT COUNT(*) AS total_tables "
    "FROM system.information_schema.tables "
    "WHERE table_type IN ('MANAGED', 'EXTERNAL') "
    "AND table_catalog <> 'hive_metastore'"
)

_SQL_LINEAGE = (
    "SELECT COUNT(DISTINCT target_table_full_name) AS pipeline_lineage_tables "
    "FROM system.access.table_lineage "
    f"WHERE event_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS "
    "AND source_table_full_name IS NOT NULL"
)

_REF = "https://docs.databricks.com/en/data-governance/unity-catalog/data-lineage.html"


@register(layer="processing", question_ids=["PRO-DG-01"])
class ProcessingLineageCheck(Check):
    """Assess lineage capture through transformation pipelines.

    Queries ``system.information_schema.tables`` for the total number of
    governed tables and ``system.access.table_lineage`` for tables that appear
    as a target with a non-null ``source_table_full_name`` (table-to-table
    lineage events), confirming that the upstream dependency of a transformation
    was recorded.  Confidence is MEDIUM because lineage coverage depends on
    whether the workload surfaces SQL-level lineage to Unity Catalog.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        total_rows = ctx.sql.query(_SQL_TOTAL)
        lineage_rows = ctx.sql.query(_SQL_LINEAGE)

        total_tables = int(
            (total_rows[0].get("total_tables") if total_rows else None) or 0
        )
        pipeline_lineage_tables = int(
            (lineage_rows[0].get("pipeline_lineage_tables") if lineage_rows else None) or 0
        )

        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{pipeline_lineage_tables} governed table(s) have table-to-table "
                    f"lineage recorded in the last {_WINDOW_DAYS} days "
                    f"(out of {total_tables} governed tables total)"
                ),
                detail=_SQL_TOTAL,
                rows=[
                    {
                        "total_tables": total_tables,
                        "pipeline_lineage_tables": pipeline_lineage_tables,
                    }
                ],
                ref=_REF,
            ),
            Evidence(
                kind="sql",
                summary=(
                    f"system.access.table_lineage: {pipeline_lineage_tables} distinct "
                    f"target table(s) with a non-null source_table_full_name "
                    f"(last {_WINDOW_DAYS} days)"
                ),
                detail=_SQL_LINEAGE,
                rows=[{"pipeline_lineage_tables": pipeline_lineage_tables}],
                ref=_REF,
            ),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total_tables"]
        with_lineage = row["pipeline_lineage_tables"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No governed tables found outside hive_metastore; "
                    "cannot assess pipeline lineage coverage."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = min(1.0, with_lineage / total)
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
                f"{with_lineage} of {total} governed tables ({ratio:.0%}) have "
                f"table-to-table lineage recorded in system.access.table_lineage "
                f"(last {_WINDOW_DAYS} days); threshold for 'met' is {_MET_THRESHOLD:.0%}. "
                "Confidence is MEDIUM: Python/Spark tasks without a SQL lineage surface "
                "may not be fully captured by Unity Catalog lineage events."
            ),
            sources=evidence,
        )
