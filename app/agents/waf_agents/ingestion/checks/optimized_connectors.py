"""Optimized connectors check (LLM-judged).

Answers:
  ING-IU-01  Use optimized connectors to ingest data sources

Signal: what source types feed the lakehouse (from ``system.access.table_lineage``
over 90 days) and how many managed pipelines exist in the workspace
(``system.lakeflow.pipelines``). Managed/Lakeflow pipelines and native source
types (DELTA, AUTO_LOADER, JDBC-via-connector, …) are indicators of optimized
ingestion; a large tail of bespoke or opaque sources is a risk signal.

Evidence is gathered purely from system tables so the check works for any
service principal without requiring REST API access to job/pipeline objects.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_LINEAGE_SQL = (
    "SELECT source_type, COUNT(*) AS n "
    "FROM system.access.table_lineage "
    "WHERE event_time >= current_timestamp() - INTERVAL 90 DAYS "
    "  AND source_type IS NOT NULL "
    "GROUP BY source_type "
    "ORDER BY n DESC"
)

_PIPELINE_SQL = "SELECT COUNT(*) AS n FROM system.lakeflow.pipelines"

_REF = "https://docs.databricks.com/en/ingestion/index.html"


@register(layer="ingestion", question_ids=["ING-IU-01"])
class OptimizedConnectorsCheck(Check):
    """LLM-judged check: weighs whether ingestion uses managed / optimized connectors
    (Lakeflow pipelines, Auto Loader, native formats) versus bespoke paths."""

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        lineage_rows = ctx.sql.query(_LINEAGE_SQL)
        pipeline_rows = ctx.sql.query(_PIPELINE_SQL)

        pipeline_count = int((pipeline_rows[0].get("n") or 0) if pipeline_rows else 0)

        if lineage_rows:
            source_summary = ", ".join(
                f"{r['source_type']}({r['n']})" for r in lineage_rows[:10]
            )
        else:
            source_summary = "no lineage data available"

        return [
            Evidence(
                kind="sql",
                summary=f"Source types feeding the lakehouse (last 90 d): {source_summary}",
                detail=_LINEAGE_SQL,
                rows=lineage_rows[:25],
                ref=_REF,
            ),
            Evidence(
                kind="sql",
                summary=(
                    f"{pipeline_count} managed pipeline(s) found "
                    "in system.lakeflow.pipelines"
                ),
                detail=_PIPELINE_SQL,
                rows=pipeline_rows,
                ref=_REF,
            ),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
