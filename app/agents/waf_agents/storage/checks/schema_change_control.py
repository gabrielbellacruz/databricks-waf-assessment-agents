"""Schema change control check (LLM-judged).

Answers:
  STO-OE-03  Manage schema changes to stored tables through change control

Signal: ALTER TABLE statements in system.query.history over the last 30
days, broken down by executed_by — whether the runner looks like a service
principal (no '@', proxy for CI/automation) or an interactive user (with
'@', proxy for ad-hoc change). The LLM judge weighs the origin mix to
assess whether schema changes go through a controlled process.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  COUNT(*) AS alter_table_count,
  SUM(CASE WHEN executed_by NOT LIKE '%@%' THEN 1 ELSE 0 END) AS sp_executed,
  SUM(CASE WHEN executed_by LIKE '%@%' THEN 1 ELSE 0 END) AS user_executed
FROM system.query.history
WHERE statement_text ILIKE '%ALTER TABLE%'
  AND start_time >= current_timestamp() - INTERVAL 30 DAYS
LIMIT 1\
"""

_REF = "https://docs.databricks.com/en/delta/delta-schema-enforcement.html"


@register(layer="storage", question_ids=["STO-OE-03"])
class SchemaChangeControlCheck(Check):
    """Assess schema-change discipline via ALTER TABLE origin in query history.

    Service-principal-driven ALTER TABLE statements (executed_by without
    '@') are treated as a proxy for CI/automation-controlled changes.
    User-driven changes (with '@') suggest ad-hoc/interactive schema edits.
    The LLM judge weighs the ratio and notes the heuristic limitation.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            alter_count = int(rows[0].get("alter_table_count") or 0)
            sp_executed = int(rows[0].get("sp_executed") or 0)
            user_executed = int(rows[0].get("user_executed") or 0)
        else:
            alter_count = 0
            sp_executed = 0
            user_executed = 0

        if alter_count > 0:
            summary = (
                f"{alter_count} ALTER TABLE statements in the last 30 days: "
                f"{sp_executed} run by service principals (automated/CI), "
                f"{user_executed} run by interactive users"
            )
        else:
            summary = (
                "No ALTER TABLE statements found in system.query.history "
                "for the last 30 days"
            )

        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=[{
                    "alter_table_count": alter_count,
                    "sp_executed": sp_executed,
                    "user_executed": user_executed,
                }],
                ref=_REF,
            )
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
