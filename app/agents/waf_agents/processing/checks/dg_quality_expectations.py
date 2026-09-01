"""Data quality expectations during processing (LLM-judged).

Answers:
  PRO-DG-02  Enforce data quality expectations during processing

Signal: the presence of Lakeflow/DLT pipelines (which support inline
expectations) from ``system.lakeflow.pipelines``, plus explicitly enforced
check constraints from ``system.information_schema.check_constraints`` and
total governed tables for context.

DLT/Lakeflow pipeline *expectations* (``@dlt.expect*`` decorators) are the
primary processing-layer quality enforcement mechanism but are NOT enumerable
via system tables; their count cannot be directly observed.  Enforced check
constraints and the pipeline count are the best available proxies.  A note
evidence records this gap; the LLM judge weighs both.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_PIPELINES = "SELECT COUNT(*) AS pipeline_count FROM system.lakeflow.pipelines"

_SQL_CHECK_CONSTRAINTS = (
    "SELECT COUNT(*) AS check_constraints "
    "FROM system.information_schema.check_constraints"
)

_SQL_TABLES = (
    "SELECT COUNT(*) AS total_tables "
    "FROM system.information_schema.tables "
    "WHERE table_type IN ('MANAGED','EXTERNAL') "
    "AND table_catalog <> 'hive_metastore'"
)

_NOTE = (
    "DLT/Lakeflow pipeline expectations (@dlt.expect, @dlt.expect_or_drop, "
    "@dlt.expect_or_fail) are the primary processing-layer quality enforcement "
    "mechanism but are NOT enumerable via system tables — only their existence "
    "as pipelines is visible.  Enforced check constraints are a partial proxy. "
    "Manual confirmation needed to assess actual expectation coverage."
)

_REF = "https://docs.databricks.com/en/delta-live-tables/expectations.html"


@register(layer="processing", question_ids=["PRO-DG-02"])
class ProcessingQualityExpectationsCheck(Check):
    """Assess data-quality expectation enforcement during processing.

    Evidence:
      1. Count of Lakeflow/DLT pipelines (proxy for expectation capability).
      2. Count of check constraints across governed tables (explicit enforcement).
      3. Total governed table count (context for interpreting low constraint counts).
      4. Note recording that pipeline expectations are not enumerable.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        pipeline_rows = ctx.sql.query(_SQL_PIPELINES)
        constraint_rows = ctx.sql.query(_SQL_CHECK_CONSTRAINTS)
        tables_rows = ctx.sql.query(_SQL_TABLES)

        pipeline_count = int(
            (pipeline_rows[0].get("pipeline_count") or 0) if pipeline_rows else 0
        )
        check_constraints = int(
            (constraint_rows[0].get("check_constraints") or 0) if constraint_rows else 0
        )
        total_tables = int(
            (tables_rows[0].get("total_tables") or 0) if tables_rows else 0
        )

        pipeline_evidence = Evidence(
            kind="sql",
            summary=(
                f"{pipeline_count} DLT/Lakeflow pipeline(s) found "
                "(each can enforce inline expectations)"
            ),
            detail=_SQL_PIPELINES,
            rows=[{"pipeline_count": pipeline_count}],
            ref=_REF,
        )
        constraint_evidence = Evidence(
            kind="sql",
            summary=(
                f"{check_constraints} check constraint(s) enforced across "
                f"{total_tables} governed table(s) in Unity Catalog"
            ),
            detail=f"{_SQL_CHECK_CONSTRAINTS} ; {_SQL_TABLES}",
            rows=[
                {
                    "check_constraints": check_constraints,
                    "total_tables": total_tables,
                }
            ],
            ref="https://docs.databricks.com/en/tables/constraints.html",
        )
        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [pipeline_evidence, constraint_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
