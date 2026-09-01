"""Metric validation check (LLM-judged).

Answers:
  ANA-R-05  Validate metrics against expectations

Metrics served to dashboards and reports must be validated against known
expectations (range checks, row-count assertions, not-null constraints, anomaly
detection). This guards against silent data quality issues propagating to
business consumers.

Observable proxies:
  - ``system.query.history``: statements containing constraint or assertion
    keywords (EXPECT, CONSTRAINT, ASSERT, CHECK, VALIDATE, row_count) indicate
    active metric validation in the workspace.
  - ``system.information_schema.table_constraints``: table-level CHECK and NOT
    NULL constraints on analytics tables provide a baseline validation layer.

What is NOT observable: whether validation results trigger alerts, whether
expectation thresholds are documented, or whether anomaly detection is wired
to downstream notifications. Manual confirmation is needed for a complete picture.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_VALIDATION_SQL = (
    "SELECT "
    "SUM(CASE WHEN statement_text ILIKE '%EXPECT%' "
    "         OR statement_text ILIKE '%ASSERT%' "
    "         OR statement_text ILIKE '% CHECK %' "
    "         OR statement_text ILIKE '%VALIDATE%' "
    "         OR statement_text ILIKE '%row_count%' "
    "THEN 1 ELSE 0 END) AS validation_stmts, "
    "COUNT(*) AS total_stmts "
    "FROM system.query.history "
    "WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS"
)

_CONSTRAINTS_SQL = (
    "SELECT constraint_type, COUNT(*) AS cnt "
    "FROM system.information_schema.table_constraints "
    "WHERE constraint_catalog <> 'hive_metastore' "
    "GROUP BY constraint_type "
    "ORDER BY cnt DESC"
)

_NOTE = (
    "Metric validation encompasses range checks, row-count assertions, not-null "
    "constraints, and anomaly detection against defined expectations. Query history "
    "can surface keyword proxies (EXPECT, ASSERT, VALIDATE, CHECK) but cannot confirm "
    "that validation is systematic or that failures trigger alerts. Table constraints "
    "indicate schema-level enforcement but not business-rule validation thresholds. "
    "Manual confirmation is required to assess whether a full metric validation framework "
    "(e.g. Great Expectations, Delta Live Tables expectations, or custom checks) is "
    "in place."
)

_REF = "https://docs.databricks.com/en/delta-live-tables/expectations.html"


@register(layer="analytics", question_ids=["ANA-R-05"])
class MetricValidationCheck(Check):
    """Assess metric validation posture via query history and table constraints.

    Evidence:
      1. Validation-keyword statement counts from query.history (last 30 days):
         EXPECT, ASSERT, CHECK, VALIDATE, row_count.
      2. Table constraint type breakdown from information_schema.table_constraints.
      3. A note recording what cannot be determined from system tables.
    The LLM judge weighs all three pieces.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        validation_rows = ctx.sql.query(_VALIDATION_SQL)
        constraint_rows = ctx.sql.query(_CONSTRAINTS_SQL)

        if validation_rows:
            row = validation_rows[0]
            validation_stmts = int(row.get("validation_stmts") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
        else:
            validation_stmts = 0
            total_stmts = 0

        if total_stmts == 0:
            validation_summary = (
                "No query history found for the last 30 days "
                "— cannot assess metric validation patterns"
            )
        else:
            pct = round(100.0 * validation_stmts / total_stmts, 1)
            validation_summary = (
                f"Validation-keyword statements (EXPECT/ASSERT/CHECK/VALIDATE/row_count) "
                f"in last 30 days: {validation_stmts} of {total_stmts} total ({pct}%)"
            )

        validation_evidence = Evidence(
            kind="sql",
            summary=validation_summary,
            detail=_VALIDATION_SQL,
            rows=[{"validation_stmts": validation_stmts, "total_stmts": total_stmts}],
            ref=_REF,
        )

        if constraint_rows:
            constraint_summary = (
                "Table constraints in information_schema: "
                + ", ".join(f"{r['constraint_type']}={r['cnt']}" for r in constraint_rows[:10])
            )
        else:
            constraint_summary = (
                "No table constraints found in "
                "system.information_schema.table_constraints"
            )

        constraint_evidence = Evidence(
            kind="sql",
            summary=constraint_summary,
            detail=_CONSTRAINTS_SQL,
            rows=constraint_rows[:10],
            ref="https://docs.databricks.com/en/sql/language-manual/sql-ref-syntax-ddl-create-table-constraint.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [validation_evidence, constraint_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
