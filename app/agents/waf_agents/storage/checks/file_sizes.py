"""File-sizes check (LLM-judged).

Answers:
  STO-PE-02  Maintain healthy file sizes in storage

Per-file size distributions are not exposed in the system tables available to
this agent.  The closest observable proxy is the frequency of OPTIMIZE commands
(compaction runs) in system.query.history over the last 30 days: regular OPTIMIZE
usage indicates the team is actively managing file sizes.  Delta also supports
Auto Optimize / auto-compaction; those settings are not visible in system tables.

A note evidence records the measurement gap explicitly.  The LLM judge weighs
OPTIMIZE frequency and is expected to lean toward unknown where the signal is
absent.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """
SELECT
  SUM(CASE WHEN statement_text ILIKE '%OPTIMIZE%' THEN 1 ELSE 0 END)
      AS optimize_stmts,
  SUM(CASE WHEN statement_text ILIKE '%VACUUM%' THEN 1 ELSE 0 END)
      AS vacuum_stmts,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS
""".strip()

_NOTE = (
    "Per-file count and file-size distribution are not exposed in the system tables "
    "available to this agent, so file-size health cannot be measured directly. "
    "OPTIMIZE frequency in query history is only an indirect proxy that compaction is "
    "being performed; whether Auto Optimize / auto-compaction is enabled at the table "
    "or session level is also not observable here. "
    "Manual confirmation via DESCRIBE DETAIL on key tables is recommended."
)

_REF = "https://docs.databricks.com/en/delta/optimize.html"


@register(layer="storage", question_ids=["STO-PE-02"])
class FileSizesCheck(Check):
    """Assess file-size health via OPTIMIZE compaction frequency in query history.

    Evidence is gathered from system.query.history (last 30 days): OPTIMIZE and
    VACUUM statement counts as proxies for active file-size management.  A note
    evidence records the measurement gap (per-file stats not available).  The
    LLM judge weighs both pieces and is expected to lean toward unknown where
    compaction commands are absent.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            optimize_stmts = int(row.get("optimize_stmts") or 0)
            vacuum_stmts = int(row.get("vacuum_stmts") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
        else:
            optimize_stmts = 0
            vacuum_stmts = 0
            total_stmts = 0

        if total_stmts == 0:
            sql_summary = (
                "No query-history rows found for the last 30 days"
                " — cannot assess OPTIMIZE/VACUUM frequency"
            )
        else:
            sql_summary = (
                f"Compaction commands (last 30 days): OPTIMIZE={optimize_stmts},"
                f" VACUUM={vacuum_stmts}; total statements={total_stmts}"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=sql_summary,
            detail=_SQL,
            rows=[
                {
                    "optimize_stmts": optimize_stmts,
                    "vacuum_stmts": vacuum_stmts,
                    "total_stmts": total_stmts,
                }
            ],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
