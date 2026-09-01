"""Rescue-invalid-data check (LLM-judged).

Answers:
  ING-R-01  Automatically rescue invalid or nonconforming incoming data

Signal: presence of the Auto Loader / DLT rescued-data column
(``_rescued_data``) across Unity Catalog tables, queried from
``system.information_schema.columns``. Auto Loader writes this column when
``rescuedDataColumn`` is configured; DLT adds it automatically when schema
enforcement is enabled. A workspace where many tables carry the column is
routinely capturing malformed records instead of silently dropping or failing
on them.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_RESCUE_SQL = """\
SELECT COUNT(DISTINCT table_catalog||'.'||table_schema||'.'||table_name)
    AS tables_with_rescue
FROM system.information_schema.columns
WHERE column_name = '_rescued_data'
  AND table_catalog <> 'hive_metastore'
"""

_TOTAL_SQL = """\
SELECT COUNT(*) AS total_tables
FROM system.information_schema.tables
WHERE table_type IN ('MANAGED', 'EXTERNAL')
  AND table_catalog <> 'hive_metastore'
"""

_REF = "https://docs.databricks.com/en/ingestion/auto-loader/schema.html#rescue"


@register(layer="ingestion", question_ids=["ING-R-01"])
class RescueInvalidDataCheck(Check):
    """Check whether ingestion pipelines rescue invalid or nonconforming data.

    Queries ``system.information_schema.columns`` for tables that carry the
    ``_rescued_data`` column (written by Auto Loader and DLT when rescue mode is
    active) and compares that count to the total number of managed/external
    tables. The ratio is evidence for the LLM judge, which weighs it against the
    WAF reliability best practice.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rescue_rows = ctx.sql.query(_RESCUE_SQL)
        total_rows = ctx.sql.query(_TOTAL_SQL)

        tables_with_rescue = 0
        if rescue_rows:
            tables_with_rescue = int(rescue_rows[0].get("tables_with_rescue") or 0)

        total_tables = 0
        if total_rows:
            total_tables = int(total_rows[0].get("total_tables") or 0)

        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{tables_with_rescue} of {total_tables} managed/external tables "
                    "carry the '_rescued_data' column"
                ),
                detail=_RESCUE_SQL.strip(),
                rows=[{"tables_with_rescue": tables_with_rescue, "total_tables": total_tables}],
                ref=_REF,
            ),
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
