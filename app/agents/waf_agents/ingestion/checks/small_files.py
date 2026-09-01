"""Small-files check (LLM-judged).

Answers:
  ING-PE-03  Avoid the small-file problem at the landing layer

Per-file counts and file-size distributions are not exposed in the system
tables available to this agent, so the small-file problem cannot be measured
directly. The closest observable proxy is the share of managed/external tables
stored in Delta format: Delta supports OPTIMIZE and auto-compaction, meaning
the tooling to address small files is at least available. Whether those tools
are actually exercised at the landing layer requires manual or DESCRIBE DETAIL
confirmation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT COUNT(*) AS total_tables,
       SUM(CASE WHEN data_source_format = 'DELTA' THEN 1 ELSE 0 END) AS delta_tables
FROM system.information_schema.tables
WHERE table_type IN ('MANAGED','EXTERNAL') AND table_catalog <> 'hive_metastore'\
"""

_NOTE_SUMMARY = (
    "File-count and file-size distribution at the landing layer are not exposed in the "
    "system tables available to this agent, so the small-file problem cannot be measured "
    "directly. Delta adoption only indicates that compaction tooling (OPTIMIZE / "
    "auto-compaction) is available, not that small files are avoided. "
    "Manual or DESCRIBE DETAIL confirmation needed."
)

_OPTIMIZE_REF = "https://docs.databricks.com/en/delta/optimize.html"


@register(layer="ingestion", question_ids=["ING-PE-03"])
class SmallFilesCheck(Check):
    """Assess small-file risk at the landing layer via Delta table adoption as a proxy.

    Direct measurement (file counts, file sizes) is not available in the system
    tables this agent can query. Delta adoption is collected as a weak enabler
    proxy: Delta tables support OPTIMIZE and auto-compaction, so their presence
    indicates compaction tooling is available. A note evidence records the
    measurement gap explicitly. The LLM judge is expected to lean toward
    ``unknown`` given the indirect signal.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            total = int(rows[0].get("total_tables") or 0)
            delta = int(rows[0].get("delta_tables") or 0)
        else:
            total = 0
            delta = 0

        if total > 0:
            pct = round(100.0 * delta / total, 1)
            summary = (
                f"{delta} of {total} managed/external tables use Delta format "
                f"({pct}%) — compaction tooling (OPTIMIZE/auto-compaction) available"
            )
        else:
            pct = 0.0
            summary = (
                "No managed or external tables found in system.information_schema.tables"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[{"total_tables": total, "delta_tables": delta, "delta_pct": pct}],
            ref=_OPTIMIZE_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE_SUMMARY,
            rows=[],
            ref=_OPTIMIZE_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
