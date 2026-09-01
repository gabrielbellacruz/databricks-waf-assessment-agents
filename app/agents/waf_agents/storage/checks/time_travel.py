"""Time-travel recovery check (LLM-judged).

Answers:
  STO-R-02  Recover stored data using time travel

Time travel is a Delta-exclusive capability.  Two evidence signals are
collected:

1. Delta-table share — from ``system.information_schema.tables``
   (data_source_format = 'DELTA').  Non-Delta tables have no time-travel
   capability, so a low Delta share sets a hard upper bound on recoverability.

2. Time-travel usage in ``system.query.history`` — statements containing
   RESTORE, VERSION AS OF, or TIMESTAMP AS OF indicate that the team
   actually exercises the capability, not just stores data in Delta.

NOTE: The effective time-travel window is controlled by
``delta.logRetentionDuration`` and ``delta.deletedFileRetentionDuration``
table properties, which are NOT visible in system.information_schema.  A
workspace may have all Delta tables yet have very short (or default 30-day)
retention.  The LLM judge should treat this as a gap and lean toward
``partial`` or ``unknown`` unless both Delta adoption and demonstrated usage
are strong.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_DELTA_TABLES_SQL = (
    "SELECT COUNT(*) AS total_tables,"
    " SUM(CASE WHEN data_source_format = 'DELTA' THEN 1 ELSE 0 END) AS delta_tables"
    " FROM system.information_schema.tables"
    " WHERE table_type IN ('MANAGED', 'EXTERNAL')"
    " AND table_catalog <> 'hive_metastore'"
)

_TIME_TRAVEL_SQL = """\
SELECT
  SUM(CASE WHEN statement_text ILIKE '%RESTORE%' THEN 1 ELSE 0 END) AS restore_stmts,
  SUM(CASE WHEN statement_text ILIKE '%VERSION AS OF%' THEN 1 ELSE 0 END) AS version_as_of_stmts,
  SUM(CASE WHEN statement_text ILIKE '%TIMESTAMP AS OF%' THEN 1 ELSE 0 END) AS timestamp_as_of_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS"""

_RETENTION_NOTE = (
    "NOTE: Delta log and deleted-file retention windows"
    " (delta.logRetentionDuration, delta.deletedFileRetentionDuration)"
    " are NOT visible in system.information_schema."
    " The effective time-travel window must be verified via DESCRIBE DETAIL"
    " or by inspecting Delta table properties directly."
)

_REF = "https://docs.databricks.com/en/delta/history.html"


@register(layer="storage", question_ids=["STO-R-02"])
class TimeTravelCheck(Check):
    """Assess time-travel recovery capability via Delta adoption and usage history.

    Delta-format adoption indicates that the capability is available; actual
    RESTORE / VERSION AS OF / TIMESTAMP AS OF usage in query history indicates
    that the capability is exercised.  Retention window limits are not
    observable from system tables — the LLM judge is given an explicit note
    about this gap and is expected to factor it into its confidence rating.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        delta_rows = ctx.sql.query(_DELTA_TABLES_SQL)
        usage_rows = ctx.sql.query(_TIME_TRAVEL_SQL)

        # --- Delta adoption signal ---
        total = int((delta_rows[0].get("total_tables") or 0) if delta_rows else 0)
        delta = int((delta_rows[0].get("delta_tables") or 0) if delta_rows else 0)
        delta_pct = round(100.0 * delta / total, 1) if total > 0 else 0.0

        delta_evidence = Evidence(
            kind="sql",
            summary=(
                f"{delta} of {total} managed/external tables use Delta format"
                f" ({delta_pct}%) — time-travel capability available on Delta tables"
            ),
            detail=_DELTA_TABLES_SQL,
            rows=[{"total_tables": total, "delta_tables": delta, "delta_pct": delta_pct}],
            ref=_REF,
        )

        # --- Time-travel usage signal ---
        usage_row = usage_rows[0] if usage_rows else {}
        restore = int(usage_row.get("restore_stmts") or 0)
        version_as_of = int(usage_row.get("version_as_of_stmts") or 0)
        timestamp_as_of = int(usage_row.get("timestamp_as_of_stmts") or 0)
        total_uses = restore + version_as_of + timestamp_as_of

        usage_evidence = Evidence(
            kind="sql",
            summary=(
                f"Time-travel usage in the last 30 days:"
                f" RESTORE={restore},"
                f" VERSION AS OF={version_as_of},"
                f" TIMESTAMP AS OF={timestamp_as_of}"
                f" (total={total_uses} statements)"
            ),
            detail=_TIME_TRAVEL_SQL,
            rows=[
                {
                    "restore_stmts": restore,
                    "version_as_of_stmts": version_as_of,
                    "timestamp_as_of_stmts": timestamp_as_of,
                }
            ],
            ref=_REF,
        )

        retention_note = Evidence(
            kind="note",
            summary=_RETENTION_NOTE,
            rows=[],
            ref=_REF,
        )

        return [delta_evidence, usage_evidence, retention_note]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
