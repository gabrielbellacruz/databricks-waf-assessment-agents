"""UDF usage check (LLM-judged).

Answers:
  PRO-PE-01  Use native engine operations over UDFs

Native Spark/SQL operations run inside the query engine and benefit from
Photon, predicate pushdown, and columnar execution.  Python UDFs and
pandas_udfs serialise data across the JVM/Python boundary, bypass many
optimisations, and are typically slower.  The closest observable proxy is the
share of statements in ``system.query.history`` that contain UDF-related
keywords (CREATE FUNCTION, pandas_udf, udf() call patterns) vs total
statements.  The LLM judge weighs that ratio together with a note explaining
the gap, and returns a verdict a reviewer can confirm or override.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  SUM(
    CASE
      WHEN statement_text ILIKE '%CREATE FUNCTION%'
        OR statement_text ILIKE '%pandas_udf%'
        OR statement_text ILIKE '%udf(%'
      THEN 1 ELSE 0
    END
  ) AS udf_stmts,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_UDF_NOTE = (
    "UDF usage counts from query history are an approximate signal — a statement may create "
    "or reference a UDF without indicating whether a native equivalent exists.  Whether "
    "specific UDFs can be replaced by built-in Spark/SQL functions requires manual or code "
    "review to confirm.  Photon-incompatible operations are also not visible here."
)

_UDF_REF = "https://docs.databricks.com/en/udf/index.html"


@register(layer="processing", question_ids=["PRO-PE-01"])
class UdfUsageCheck(Check):
    """Assess native-operation usage by counting UDF-related patterns in query history.

    Evidence is gathered from ``system.query.history`` (last 30 days).  A
    count of statements containing UDF keywords (CREATE FUNCTION, pandas_udf,
    udf() patterns) vs total statements is reported.  A note evidence records
    that the signal is approximate and that manual review is needed.  The LLM judge
    weighs both pieces and produces a verdict.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            udf_stmts = int(row.get("udf_stmts") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
        else:
            udf_stmts = 0
            total_stmts = 0

        if total_stmts == 0:
            summary = (
                "No query-history rows found for the last 30 days"
                " — cannot assess UDF usage"
            )
        else:
            udf_pct = round(100.0 * udf_stmts / total_stmts, 1)
            summary = (
                f"{udf_stmts} of {total_stmts} statements ({udf_pct}%) reference a UDF "
                f"(CREATE FUNCTION / pandas_udf / udf() pattern) in the last 30 days"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[{"udf_stmts": udf_stmts, "total_stmts": total_stmts}],
            ref=_UDF_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_UDF_NOTE,
            rows=[],
            ref=_UDF_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
