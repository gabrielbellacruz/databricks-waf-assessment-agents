"""Storage versioning and recovery check (LLM-judged).

Answers:
  STO-SCP-04  Enable storage versioning for recovery

Signal: Delta Lake provides built-in table-layer versioning via its
transaction log, enabling time travel and point-in-time recovery.  The count
and share of Delta-format tables (``data_source_format = 'DELTA'``) in Unity
Catalog is used as the primary proxy for recoverable versioning at the table
layer.

Underlying cloud bucket/object versioning (S3 Object Versioning, Azure Blob
versioning, GCS Object Versioning) is configured at the cloud/account level
and is NOT visible to the agent from workspace system tables; a note evidence
item records this limitation.  The LLM judge weighs Delta adoption as a
proxy for versioning capability.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_DELTA_TABLE_SQL = (
    "SELECT COUNT(*) AS total_tables,"
    " SUM(CASE WHEN data_source_format = 'DELTA' THEN 1 ELSE 0 END) AS delta_table_count"
    " FROM system.information_schema.tables"
    " WHERE table_type IN ('MANAGED', 'EXTERNAL')"
    " AND table_catalog <> 'hive_metastore'"
)

_VERSIONING_NOTE = (
    "Delta Lake provides table-layer versioning via its transaction log, enabling time travel "
    "and point-in-time recovery. However, underlying cloud bucket/object versioning "
    "(e.g. S3 Object Versioning, Azure Blob versioning, GCS Object Versioning) is configured "
    "at the cloud/account level and is NOT visible to the agent from workspace system tables. "
    "A high Delta-table share indicates strong table-level versioning capability; "
    "bucket-level versioning status requires admin confirmation."
)

_REF = "https://docs.databricks.com/en/delta/history.html"


@register(layer="storage", question_ids=["STO-SCP-04"])
class StorageVersioningCheck(Check):
    """Assess storage versioning readiness via Delta Lake table share.

    Evidence is gathered from ``system.information_schema.tables``: the count
    and share of Delta-format tables among all managed/external UC tables.
    A companion note records that cloud bucket/object versioning is not visible
    from system tables; admin confirmation is needed for that layer. The LLM
    judge weighs Delta adoption as a proxy.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_DELTA_TABLE_SQL)

        row = rows[0] if rows else {}
        total_tables = int(row.get("total_tables") or 0)
        delta_table_count = int(row.get("delta_table_count") or 0)
        pct = (
            round(100.0 * delta_table_count / total_tables, 1) if total_tables > 0 else 0.0
        )

        delta_evidence = Evidence(
            kind="sql",
            summary=(
                f"{delta_table_count} of {total_tables} managed/external UC tables use Delta "
                f"format ({pct}%); Delta tables have built-in versioning via the transaction log"
            ),
            detail=_DELTA_TABLE_SQL,
            rows=[{"total_tables": total_tables, "delta_table_count": delta_table_count}],
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_VERSIONING_NOTE,
            rows=[],
            ref=_REF,
        )
        return [delta_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
