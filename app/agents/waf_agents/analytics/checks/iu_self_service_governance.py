"""Self-service analytics with governance check (LLM-judged).

Answers:
  ANA-IU-03  Provide self-service analytics with governance

Signals:
  * ``system.compute.warehouses`` — presence of SQL warehouses enables self-service
    querying without cluster management.
  * ``system.information_schema.table_privileges`` — total grants, distinct grantees,
    and broad/public grants (grantee = 'account users' or ILIKE '%PUBLIC%').
    A high fraction of broad grants suggests open access (permissive self-service);
    too few grants may mean access is locked down without self-service paths.
  * ``system.information_schema.tables`` — UC table coverage excluding hive_metastore,
    since Unity Catalog governance is the prerequisite for governed self-service.

The LLM judge weighs whether SQL warehouses exist alongside governance signals
(UC tables with controlled grants) that indicate governed — not ungoverned — self-service.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WAREHOUSE_SQL = (
    "SELECT COUNT(*) AS total_warehouses,"
    " SUM(CASE WHEN state = 'RUNNING' THEN 1 ELSE 0 END) AS running_warehouses"
    " FROM system.compute.warehouses"
)

_GRANT_ANALYSIS_SQL = (
    "SELECT COUNT(*) AS total_grants,"
    " COUNT(DISTINCT grantee) AS distinct_grantees,"
    " SUM(CASE WHEN grantee = 'account users'"
    "          OR grantee ILIKE '%PUBLIC%' THEN 1 ELSE 0 END) AS broad_grants"
    " FROM system.information_schema.table_privileges"
    " WHERE table_catalog <> 'hive_metastore'"
)

_UC_COVERAGE_SQL = (
    "SELECT COUNT(*) AS uc_tables"
    " FROM system.information_schema.tables"
    " WHERE table_type IN ('MANAGED','EXTERNAL')"
    " AND table_catalog <> 'hive_metastore'"
)

_REF = (
    "https://docs.databricks.com/en/data-governance/unity-catalog/"
    "manage-privileges/privileges.html"
)


@register(layer="analytics", question_ids=["ANA-IU-03"])
class SelfServiceGovernanceCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        wh_rows = ctx.sql.query(_WAREHOUSE_SQL)
        grant_rows = ctx.sql.query(_GRANT_ANALYSIS_SQL)
        uc_rows = ctx.sql.query(_UC_COVERAGE_SQL)

        wrow = wh_rows[0] if wh_rows else {}
        total_warehouses = int(wrow.get("total_warehouses") or 0)
        running_warehouses = int(wrow.get("running_warehouses") or 0)

        grow = grant_rows[0] if grant_rows else {}
        total_grants = int(grow.get("total_grants") or 0)
        distinct_grantees = int(grow.get("distinct_grantees") or 0)
        broad_grants = int(grow.get("broad_grants") or 0)

        uc_tables = int(
            (uc_rows[0].get("uc_tables") or 0) if uc_rows else 0
        )

        broad_pct = (
            round(100.0 * broad_grants / total_grants, 1) if total_grants > 0 else 0.0
        )

        warehouse_evidence = Evidence(
            kind="sql",
            summary=(
                f"{total_warehouses} SQL warehouse(s) ({running_warehouses} running);"
                " warehouses are the primary self-service analytics gateway"
            ),
            detail=_WAREHOUSE_SQL,
            rows=wh_rows[:10],
            ref=_REF,
        )
        grant_evidence = Evidence(
            kind="sql",
            summary=(
                f"{total_grants} UC table grants across {distinct_grantees} distinct grantees;"
                f" {broad_grants} broad/public grants ({broad_pct}%)"
            ),
            detail=_GRANT_ANALYSIS_SQL,
            rows=grant_rows[:5],
            ref=_REF,
        )
        uc_evidence = Evidence(
            kind="sql",
            summary=(
                f"{uc_tables} managed/external tables in Unity Catalog (UC governance"
                " is the prerequisite for governed self-service access)"
            ),
            detail=_UC_COVERAGE_SQL,
            rows=uc_rows[:3],
            ref=_REF,
        )
        return [warehouse_evidence, grant_evidence, uc_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
