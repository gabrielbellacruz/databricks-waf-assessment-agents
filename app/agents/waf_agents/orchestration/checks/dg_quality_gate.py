"""Data-quality gating in orchestration check (LLM-judged).

Answers:
  ORC-DG-05  Gate workflow progression on data quality

Two workspace-wide SQL signals are gathered via ctx.sql:
  1. Recent query-history statements containing data-quality framework keywords
     (CONSTRAINT, EXPECT, great_expectations, deequ) in the last 30 days
     (``system.query.history``). These keywords appear in DLT pipeline
     definitions, dbt tests, and custom DQ scripts — all patterns that gate
     downstream steps on data quality.
  2. Count of active DLT pipelines (``system.lakeflow.pipelines``). DLT has
     first-class ``EXPECT`` constraints that halt or quarantine bad data; a
     non-zero count is a strong proxy for quality gating at the pipeline layer.

The LLM judge weighs both signals.  Neither proves that *workflow progression*
(e.g. a downstream job waiting on a DQ step to pass) is enforced end-to-end,
so confidence is capped at medium.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 30

_SQL_DQ_HISTORY = (
    "SELECT COUNT(*) AS dq_statements "
    "FROM system.query.history "
    "WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS "
    "AND (statement_text ILIKE '%CONSTRAINT%' "
    "  OR statement_text ILIKE '%EXPECT(%' "
    "  OR statement_text ILIKE '%great_expectations%' "
    "  OR statement_text ILIKE '%deequ%')"
)

_SQL_PIPELINES = (
    "SELECT COUNT(*) AS dlt_pipelines "
    "FROM system.lakeflow.pipelines"
)

_NOTE_SUMMARY = (
    "Whether workflow *progression* is explicitly gated on data-quality outcomes "
    "(e.g. a downstream job only starts after a DQ check task passes) is an "
    "orchestration design choice not directly visible in system tables. DQ statement "
    "frequency and DLT pipeline counts are indirect indicators. Manual confirmation needed."
)

_REF = (
    "https://docs.databricks.com/en/delta-live-tables/expectations.html"
)


@register(layer="orchestration", question_ids=["ORC-DG-05"])
class QualityGateCheck(Check):
    """LLM-judged check for ORC-DG-05: gating workflow progression on data quality.

    Evidence collected:
      1. DQ-framework statement count from query history (kind ``sql``).
      2. Active DLT pipeline count from system.lakeflow.pipelines (kind ``sql``).
      3. Caveat note on measurement limits (kind ``note``).
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        # --- evidence 1: DQ keywords in query history ---
        dq_rows = ctx.sql.query(_SQL_DQ_HISTORY)
        dq_row = dq_rows[0] if dq_rows else {}
        dq_statements = int(dq_row.get("dq_statements") or 0)
        ev_dq = Evidence(
            kind="sql",
            summary=(
                f"{dq_statements} query-history statement(s) in the last {_WINDOW_DAYS} days "
                "reference DQ keywords (CONSTRAINT, EXPECT, great_expectations, deequ)"
            ),
            detail=_SQL_DQ_HISTORY,
            rows=[{"dq_statements": dq_statements}],
            ref=_REF,
        )

        # --- evidence 2: active DLT pipelines ---
        pl_rows = ctx.sql.query(_SQL_PIPELINES)
        pl_row = pl_rows[0] if pl_rows else {}
        dlt_pipelines = int(pl_row.get("dlt_pipelines") or 0)
        ev_pipelines = Evidence(
            kind="sql",
            summary=(
                f"{dlt_pipelines} active DLT pipeline(s) found — "
                "DLT EXPECT constraints gate record progression natively"
            ),
            detail=_SQL_PIPELINES,
            rows=[{"dlt_pipelines": dlt_pipelines}],
            ref=_REF,
        )

        ev_note = Evidence(
            kind="note",
            summary=_NOTE_SUMMARY,
            rows=[],
            ref=_REF,
        )

        return [ev_dq, ev_pipelines, ev_note]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
