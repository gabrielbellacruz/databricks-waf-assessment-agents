"""Cold data tiering check (LLM-judged).

Answers:
  STO-CO-03  Tier cold data to cheaper storage

Signal: tables with no read activity in system.access.table_lineage in the last 90
days ("cold tables") versus the total count of managed/external Unity Catalog tables.
A large proportion of cold tables with no evidence of tiering to cheaper storage is
an opportunity indicator. Cloud storage-class tiering (S3 Glacier, GCS Nearline,
Azure Cool/Archive) is NOT directly observable from Databricks system tables — this
check can identify cold tables but cannot confirm whether they are physically tiered.
The LLM judge is expected to return a low-confidence verdict reflecting this gap.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 90

_SQL_TOTAL = (
    "SELECT COUNT(*) AS total_tables "
    "FROM system.information_schema.tables "
    "WHERE table_type IN ('MANAGED', 'EXTERNAL') "
    "AND table_catalog <> 'hive_metastore'"
)

_SQL_RECENTLY_READ = (
    "SELECT COUNT(DISTINCT source_table_full_name) AS recently_read_tables "
    "FROM system.access.table_lineage "
    f"WHERE event_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS "
    "AND source_table_full_name IS NOT NULL "
    "LIMIT 10000"
)

_NOTE_LIMIT = (
    "Cloud storage-class tiering (S3 Glacier, GCS Nearline, Azure Cool/Archive) is not "
    "observable from Databricks system tables. This check identifies tables with no "
    "recorded lineage read events as a cold-data proxy, but cannot confirm whether "
    "those tables reside on cheaper storage tiers. Also note: lineage events cover "
    "Unity Catalog tables only and may under-count reads made via direct DBFS or "
    "file-path access. Manual verification is required for a definitive assessment."
)

_REF = "https://docs.databricks.com/en/delta/index.html"


@register(layer="storage", question_ids=["STO-CO-03"])
class ColdDataTieringCheck(Check):
    """Estimate cold-data share using lineage read events as a proxy.

    Two SQL queries are issued: one for total UC table count and one for the
    count of distinct tables with at least one read in the last 90 days. The
    difference is the cold-table estimate. A note records the inherent limitation
    so the LLM judge can factor it in.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        total_rows = ctx.sql.query(_SQL_TOTAL)
        read_rows = ctx.sql.query(_SQL_RECENTLY_READ)

        total = int((total_rows[0].get("total_tables") or 0) if total_rows else 0)
        recently_read = int(
            (read_rows[0].get("recently_read_tables") or 0) if read_rows else 0
        )
        cold = max(total - recently_read, 0)
        cold_pct = round(100.0 * cold / total, 1) if total > 0 else 0.0

        sql_evidence = Evidence(
            kind="sql",
            summary=(
                f"{cold} of {total} managed/external UC tables ({cold_pct}%) had no "
                f"read activity in system.access.table_lineage in the last {_WINDOW_DAYS} days "
                f"({recently_read} table(s) had at least one read)"
            ),
            detail=_SQL_TOTAL + " | " + _SQL_RECENTLY_READ,
            rows=[
                {
                    "total_tables": total,
                    "recently_read_tables": recently_read,
                    "cold_tables": cold,
                    "cold_pct": cold_pct,
                }
            ],
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_NOTE_LIMIT,
            ref=_REF,
        )
        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
