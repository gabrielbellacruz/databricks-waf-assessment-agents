"""Data deletion and privacy request support check (LLM-judged).

Answers:
  STO-SCP-05  Support data deletion and privacy requests on stored data

Signal:
  1. DELETE statements in ``system.query.history`` over the last 90 days
     (``statement_text ILIKE '%DELETE FROM%'``) as evidence that table-layer
     deletion is actively exercised.
  2. Share of Delta-format tables (``data_source_format = 'DELTA'``) vs
     formats that do not natively support row-level DELETE or deletion
     vectors (Parquet, CSV, ORC, etc.).

A note records that the end-to-end GDPR/erasure process (request tracking,
orchestration, audit logging, proof-of-erasure) is NOT observable from
workspace system tables.  The LLM judge weighs both signals to assess
whether data deletion and privacy requests are technically supportable.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_DELETE_HISTORY_SQL = """\
SELECT
  SUM(CASE WHEN statement_text ILIKE '%DELETE FROM%' THEN 1 ELSE 0 END) AS delete_stmts,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 90 DAYS\
"""

_DELTA_FORMAT_SQL = (
    "SELECT COUNT(*) AS total_tables,"
    " SUM(CASE WHEN data_source_format = 'DELTA' THEN 1 ELSE 0 END) AS delta_format_count"
    " FROM system.information_schema.tables"
    " WHERE table_type IN ('MANAGED', 'EXTERNAL')"
    " AND table_catalog <> 'hive_metastore'"
)

_DELETION_NOTE = (
    "Row-level DELETE, MERGE, and deletion vectors are supported on Delta tables and provide "
    "the technical foundation for privacy-request fulfilment. However, the end-to-end "
    "GDPR/erasure process (request intake, orchestration, audit logging, proof-of-erasure) "
    "is NOT observable from workspace system tables. The DELETE-statement count in query "
    "history and the Delta table share are proxies for technical capability only; the full "
    "deletion workflow and compliance posture require manual confirmation."
)

_REF = "https://docs.databricks.com/en/delta/delete-from.html"


@register(layer="storage", question_ids=["STO-SCP-05"])
class DataDeletionCheck(Check):
    """Assess technical support for data deletion and privacy requests.

    Evidence is gathered from:
    - ``system.query.history``: count of DELETE FROM statements over the last
      90 days — evidence that table-layer deletion is actively exercised.
    - ``system.information_schema.tables``: share of Delta-format tables,
      which support row-level DELETE and deletion vectors; non-Delta formats
      generally do not.
    A note records that the full GDPR/erasure process is not observable from
    system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        delete_rows = ctx.sql.query(_DELETE_HISTORY_SQL)
        format_rows = ctx.sql.query(_DELTA_FORMAT_SQL)

        if delete_rows:
            r = delete_rows[0]
            delete_stmts = int(r.get("delete_stmts") or 0)
            total_stmts = int(r.get("total_stmts") or 0)
            delete_evidence = Evidence(
                kind="sql",
                summary=(
                    f"{delete_stmts} DELETE FROM statement(s) in query history "
                    f"(last 90 days, out of {total_stmts} total statements); "
                    "presence of DELETE activity is a proxy for deletion capability "
                    "being exercised"
                ),
                detail=_DELETE_HISTORY_SQL,
                rows=[{"delete_stmts": delete_stmts, "total_stmts": total_stmts}],
                ref=_REF,
            )
        else:
            delete_evidence = Evidence(
                kind="sql",
                summary=(
                    "No query-history rows returned for the last 90 days — "
                    "cannot assess DELETE statement activity"
                ),
                detail=_DELETE_HISTORY_SQL,
                rows=[],
                ref=_REF,
            )

        total_tables = int((format_rows[0].get("total_tables") or 0) if format_rows else 0)
        delta_format_count = int(
            (format_rows[0].get("delta_format_count") or 0) if format_rows else 0
        )
        pct = (
            round(100.0 * delta_format_count / total_tables, 1) if total_tables > 0 else 0.0
        )

        format_evidence = Evidence(
            kind="sql",
            summary=(
                f"{delta_format_count} of {total_tables} managed/external UC tables use "
                f"Delta format ({pct}%); Delta supports row-level DELETE and deletion "
                "vectors — non-Delta formats (Parquet, CSV, etc.) generally do not"
            ),
            detail=_DELTA_FORMAT_SQL,
            rows=[{"total_tables": total_tables, "delta_format_count": delta_format_count}],
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_DELETION_NOTE,
            rows=[],
            ref=_REF,
        )
        return [delete_evidence, format_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
