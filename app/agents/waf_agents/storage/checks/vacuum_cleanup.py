"""VACUUM and obsolete file cleanup check (LLM-judged).

Answers:
  STO-CO-02  Vacuum and clean up obsolete stored files

Signal: VACUUM statement frequency in system.query.history over the last 90 days
(statement_text ILIKE '%VACUUM%'). A low or zero count on workspaces with many Delta
tables suggests obsolete files and old version data may be accumulating. Note:
Predictive Optimization vacuums Delta tables automatically and those operations are
NOT recorded as user-issued VACUUM statements in system.query.history; a zero count
does not prove neglect when Predictive Optimization is enabled. The LLM judge weighs
the frequency count and the caveat together.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 90
_LIMIT = 1000

_SQL_VACUUM = (
    "SELECT COUNT(*) AS vacuum_statements "
    "FROM system.query.history "
    "WHERE statement_text ILIKE '%VACUUM%' "
    f"  AND start_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS "
    f"LIMIT {_LIMIT}"
)

_NOTE_PO = (
    "Predictive Optimization (enabled on DBR / serverless compute) vacuums Delta tables "
    "automatically. Those operations are system-managed and are NOT recorded as "
    "user-issued VACUUM statements in system.query.history. A low or zero user-VACUUM "
    "count is therefore not conclusive when Predictive Optimization may be enabled. "
    "A reviewer should verify Predictive Optimization status to interpret this signal correctly."
)

_REF = "https://docs.databricks.com/en/delta/vacuum.html"


@register(layer="storage", question_ids=["STO-CO-02"])
class VacuumCleanupCheck(Check):
    """Assess whether obsolete Delta files are being cleaned up via VACUUM.

    Counts user-issued VACUUM statements in query history; attaches a note about
    Predictive Optimization so the LLM judge knows the signal may under-count vacuuming.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL_VACUUM)
        count = int((rows[0].get("vacuum_statements") or 0) if rows else 0)

        sql_evidence = Evidence(
            kind="sql",
            summary=(
                f"{count} VACUUM statement(s) executed in the last {_WINDOW_DAYS} days "
                "(user-issued only — Predictive Optimization vacuums are not visible)"
            ),
            detail=_SQL_VACUUM,
            rows=[{"vacuum_statements": count}],
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_NOTE_PO,
            ref=_REF,
        )
        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
