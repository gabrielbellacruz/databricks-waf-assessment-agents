"""Row/column-level security on analytics check (LLM-judged).

Answers:
  ANA-DG-03  Apply row/column-level security to analytics

Signals:
  * ``system.information_schema.table_privileges`` — total grants on UC tables,
    group/service-principal vs individual-user grants, and broad public grants.
    Granular per-group ACLs are a prerequisite for effective row/column security.
  * ``system.information_schema.column_masks`` — column masking policies applied
    within Unity Catalog (best-effort; returns zero rows on workspaces without
    column masks configured).

Limitation: row-filter functions (applied via ALTER TABLE ... SET ROW FILTER) are
stored per-catalog in ``INFORMATION_SCHEMA.TABLE_ROW_FILTERS``, which is not
accessible through the agent SP's workspace-level system tables.  The LLM judge
should treat empty column_masks and no per-group grants as a negative signal.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_PRIVILEGE_SUMMARY_SQL = (
    "SELECT COUNT(*) AS total_grants,"
    " SUM(CASE WHEN grantee LIKE '%@%' THEN 1 ELSE 0 END) AS user_grants,"
    " SUM(CASE WHEN grantee NOT LIKE '%@%' THEN 1 ELSE 0 END) AS group_grants,"
    " SUM(CASE WHEN grantee = 'account users'"
    "          OR grantee ILIKE '%PUBLIC%' THEN 1 ELSE 0 END) AS broad_grants"
    " FROM system.information_schema.table_privileges"
    " WHERE table_catalog <> 'hive_metastore'"
)

_COLUMN_MASKS_SQL = (
    "SELECT COUNT(*) AS masked_columns,"
    " COUNT(DISTINCT catalog_name || '.' || schema_name || '.' || table_name)"
    "   AS masked_tables"
    " FROM system.information_schema.column_masks"
)

_ROW_FILTER_LIMITATION = (
    "Row-filter policies (ALTER TABLE ... SET ROW FILTER) are stored per-catalog in"
    " INFORMATION_SCHEMA.TABLE_ROW_FILTERS, which is not visible to the agent SP's"
    " workspace-level system.information_schema queries."
    " Column masks are queried via system.information_schema.column_masks;"
    " zero results may mean no masks are configured OR the view is not accessible."
)

_REF = (
    "https://docs.databricks.com/en/tables/row-and-column-filters.html"
)


@register(layer="analytics", question_ids=["ANA-DG-03"])
class RowColumnSecurityCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        priv_rows = ctx.sql.query(_PRIVILEGE_SUMMARY_SQL)
        mask_rows = ctx.sql.query(_COLUMN_MASKS_SQL)

        prow = priv_rows[0] if priv_rows else {}
        total_grants = int(prow.get("total_grants") or 0)
        user_grants = int(prow.get("user_grants") or 0)
        group_grants = int(prow.get("group_grants") or 0)
        broad_grants = int(prow.get("broad_grants") or 0)

        mrow = mask_rows[0] if mask_rows else {}
        masked_columns = int(mrow.get("masked_columns") or 0)
        masked_tables = int(mrow.get("masked_tables") or 0)

        broad_pct = (
            round(100.0 * broad_grants / total_grants, 1) if total_grants > 0 else 0.0
        )

        privilege_evidence = Evidence(
            kind="sql",
            summary=(
                f"{total_grants} total UC table grants; {group_grants} to groups/"
                f"service-principals, {user_grants} to individual users,"
                f" {broad_grants} broad/public ({broad_pct}%)"
            ),
            detail=_PRIVILEGE_SUMMARY_SQL,
            rows=priv_rows[:5],
            ref=_REF,
        )
        mask_evidence = Evidence(
            kind="sql",
            summary=(
                f"{masked_columns} column mask(s) applied across {masked_tables} table(s)"
                " in Unity Catalog"
            ),
            detail=_COLUMN_MASKS_SQL,
            rows=mask_rows[:5],
            ref=_REF,
        )
        limitation_evidence = Evidence(
            kind="uc_metadata",
            summary=_ROW_FILTER_LIMITATION,
            detail=(
                "To inspect row filters per catalog, run:"
                " SELECT * FROM <catalog>.INFORMATION_SCHEMA.TABLE_ROW_FILTERS"
            ),
            ref=_REF,
        )
        return [privilege_evidence, mask_evidence, limitation_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
