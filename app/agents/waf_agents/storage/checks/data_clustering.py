"""Data clustering check (LLM-judged).

Answers:
  STO-PE-01  Cluster stored data for common query patterns

Delta layout properties (clusteringColumns, partitioning) and liquid clustering
enablement are not exposed in system.information_schema.  The closest observable
proxy is whether clustering-related DDL/DML commands appear in query history:
  - CLUSTER BY      (liquid clustering, Delta 3.x+)
  - ZORDER BY       (legacy Z-ordering via OPTIMIZE ... ZORDER BY)
  - PARTITIONED BY  (static partitioning in CREATE TABLE / REPLACE TABLE)

All are counted over the last 30 days.  The LLM judge weighs the presence and
relative mix of these signals and returns a verdict.  Where all counts are zero
the verdict should lean toward unknown.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """
SELECT
  SUM(CASE WHEN statement_text ILIKE '%CLUSTER BY%' THEN 1 ELSE 0 END)
      AS liquid_cluster_stmts,
  SUM(CASE WHEN statement_text ILIKE '%ZORDER BY%' THEN 1 ELSE 0 END)
      AS zorder_stmts,
  SUM(CASE WHEN statement_text ILIKE '%PARTITIONED BY%' THEN 1 ELSE 0 END)
      AS partition_stmts,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS
""".strip()

_NOTE = (
    "Delta layout properties (clusteringColumns, partitioning, dataSkippingNumIndexedCols) "
    "and Predictive-Optimization-managed layout changes are not exposed in "
    "system.information_schema. This check uses query-history keyword proxies only; "
    "manual confirmation via DESCRIBE DETAIL on key tables is recommended."
)

_REF = "https://docs.databricks.com/en/delta/clustering.html"


@register(layer="storage", question_ids=["STO-PE-01"])
class DataClusteringCheck(Check):
    """Assess whether stored data is clustered for common query patterns.

    Evidence is gathered from system.query.history over the last 30 days:
    statements containing CLUSTER BY (liquid clustering), ZORDER BY (legacy
    Z-ordering), and PARTITIONED BY (static partition DDL) are counted.  A note
    evidence records the observability gap (layout metadata is not in
    information_schema). The LLM judge weighs both pieces.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            liquid_cluster_stmts = int(row.get("liquid_cluster_stmts") or 0)
            zorder_stmts = int(row.get("zorder_stmts") or 0)
            partition_stmts = int(row.get("partition_stmts") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
        else:
            liquid_cluster_stmts = 0
            zorder_stmts = 0
            partition_stmts = 0
            total_stmts = 0

        if total_stmts == 0:
            sql_summary = (
                "No query-history rows found for the last 30 days"
                " — cannot assess clustering commands"
            )
        else:
            sql_summary = (
                f"Clustering commands (last 30 days): CLUSTER BY={liquid_cluster_stmts},"
                f" ZORDER BY={zorder_stmts}, PARTITIONED BY={partition_stmts};"
                f" total statements={total_stmts}"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=sql_summary,
            detail=_SQL,
            rows=[
                {
                    "liquid_cluster_stmts": liquid_cluster_stmts,
                    "zorder_stmts": zorder_stmts,
                    "partition_stmts": partition_stmts,
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
