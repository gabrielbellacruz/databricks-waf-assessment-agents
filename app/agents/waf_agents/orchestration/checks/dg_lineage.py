"""End-to-end lineage across orchestrated steps check (LLM-judged).

Answers:
  ORC-DG-02  Track end-to-end lineage across orchestrated steps

Two workspace-wide SQL signals are gathered via ctx.sql:
  1. Governed tables that appear as a lineage target in the last 90 days
     (``system.access.table_lineage``). Lineage events recorded by job runs
     confirm that the platform captured data movement through orchestrated steps.
  2. Count of active workflow jobs (``system.lakeflow.jobs``).

The LLM judge weighs both signals.  Lineage presence is a proxy: it confirms
events were recorded but does not distinguish which jobs drove the writes or
whether cross-layer lineage is fully captured.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 90

_SQL_LINEAGE = (
    "SELECT COUNT(*) AS governed_tables, "
    "SUM(CASE WHEN t.full_name IN ("
    "SELECT DISTINCT target_table_full_name FROM system.access.table_lineage "
    f"WHERE event_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS"
    ") THEN 1 ELSE 0 END) AS tables_with_lineage "
    "FROM ("
    "SELECT table_catalog || '.' || table_schema || '.' || table_name AS full_name "
    "FROM system.information_schema.tables "
    "WHERE table_type IN ('MANAGED', 'EXTERNAL') AND table_catalog <> 'hive_metastore'"
    ") t"
)

_SQL_JOBS = (
    "SELECT COUNT(*) AS total_jobs "
    "FROM system.lakeflow.jobs "
    "WHERE delete_time IS NULL"
)

_REF = (
    "https://docs.databricks.com/en/data-governance/unity-catalog/data-lineage.html"
)


@register(layer="orchestration", question_ids=["ORC-DG-02"])
class OrchestratedLineageCheck(Check):
    """LLM-judged check for ORC-DG-02: end-to-end lineage across orchestrated steps.

    Evidence collected:
      1. Governed tables with lineage events in the last 90 days
         (system.access.table_lineage + system.information_schema.tables).
      2. Count of active workflow jobs (system.lakeflow.jobs).

    Lineage presence is a proxy: it confirms that the Unity Catalog lineage
    capture was active for those tables, but not that every orchestrated step
    is individually tracked end-to-end.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        # --- evidence 1: lineage coverage across governed tables ---
        lineage_rows = ctx.sql.query(_SQL_LINEAGE)
        lineage_row = lineage_rows[0] if lineage_rows else {}
        governed = int(lineage_row.get("governed_tables") or 0)
        with_lineage = int(lineage_row.get("tables_with_lineage") or 0)
        pct = round(100.0 * with_lineage / governed, 1) if governed > 0 else 0.0
        ev_lineage = Evidence(
            kind="sql",
            summary=(
                f"{with_lineage} of {governed} governed tables have lineage recorded "
                f"in the last {_WINDOW_DAYS} days ({pct}%)"
            ),
            detail=_SQL_LINEAGE,
            rows=[{"governed_tables": governed, "tables_with_lineage": with_lineage}],
            ref=_REF,
        )

        # --- evidence 2: active workflow jobs ---
        job_rows = ctx.sql.query(_SQL_JOBS)
        job_row = job_rows[0] if job_rows else {}
        total_jobs = int(job_row.get("total_jobs") or 0)
        ev_jobs = Evidence(
            kind="sql",
            summary=f"{total_jobs} active workflow job(s) registered in system.lakeflow.jobs",
            detail=_SQL_JOBS,
            rows=[{"total_jobs": total_jobs}],
            ref=_REF,
        )

        return [ev_lineage, ev_jobs]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
