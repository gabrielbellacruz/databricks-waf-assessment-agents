"""Table constraints check (deterministic).

Answers:
  STO-R-04  Enforce constraints on stored tables

Signal: share of managed/external tables (outside hive_metastore) that have
at least one declared constraint, derived from two separate queries:
  1. ``system.information_schema.tables`` -> denominator (total tables)
  2. ``system.information_schema.table_constraints`` -> numerator (distinct
     tables that appear in the constraints view)

Constraints are relatively rare in practice, so thresholds are set lower
than other ratio checks: met >= 50 %, partial >= 20 %.
Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.50
_PARTIAL_THRESHOLD = 0.20


@register(layer="storage", question_ids=["STO-R-04"])
class TableConstraintsCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        # Query 1: total managed/external tables outside hive_metastore.
        sql_tables = (
            "SELECT COUNT(*) AS total_tables "
            "FROM system.information_schema.tables "
            "WHERE table_type IN ('MANAGED', 'EXTERNAL') "
            "AND table_catalog <> 'hive_metastore'"
        )
        rows_tables = ctx.sql.query(sql_tables)
        total_tables = int(
            (rows_tables[0].get("total_tables") if rows_tables else None) or 0
        )

        # Query 2: distinct tables that have at least one declared constraint.
        sql_constraints = (
            "SELECT COUNT(DISTINCT "
            "table_catalog || '.' || table_schema || '.' || table_name"
            ") AS constrained_tables "
            "FROM system.information_schema.table_constraints "
            "WHERE table_catalog <> 'hive_metastore'"
        )
        rows_constraints = ctx.sql.query(sql_constraints)
        constrained_tables = int(
            (rows_constraints[0].get("constrained_tables") if rows_constraints else None) or 0
        )

        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{constrained_tables} of {total_tables} managed/external tables "
                    f"have at least one declared constraint"
                ),
                detail=sql_tables,
                rows=[{"total_tables": total_tables, "constrained_tables": constrained_tables}],
                ref=(
                    "https://docs.databricks.com/en/sql/language-manual/"
                    "sql-ref-syntax-ddl-alter-table.html"
                ),
            ),
            Evidence(
                kind="sql",
                summary=(
                    f"Constraint coverage: {constrained_tables} distinct table(s) appear "
                    f"in information_schema.table_constraints"
                ),
                detail=sql_constraints,
                rows=[{"constrained_tables": constrained_tables}],
                ref=(
                    "https://docs.databricks.com/en/sql/language-manual/"
                    "information-schema/table_constraints.html"
                ),
            ),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total_tables = row["total_tables"]
        constrained_tables = row["constrained_tables"]

        if total_tables == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No managed or external tables found outside hive_metastore; "
                    "cannot assess constraint coverage."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = min(1.0, constrained_tables / total_tables)
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
                f"{constrained_tables} of {total_tables} managed/external tables "
                f"({ratio:.0%}) have at least one declared constraint; "
                f"threshold for 'met' is ≥{_MET_THRESHOLD:.0%}."
            ),
            sources=evidence,
        )
