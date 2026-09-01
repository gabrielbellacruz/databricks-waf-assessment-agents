"""Encryption and access control check for stored data (LLM-judged).

Answers:
  STO-SCP-01  Encrypt stored data and restrict access

Signal: governed-storage posture from system.information_schema —
count of external locations and storage credentials (governed cloud-path
registration), the share of EXTERNAL tables in Unity Catalog (UC external
tables are required to reference registered external locations, providing a
governance proxy), and grant breadth from table_privileges (broad/public
grants vs total).

At-rest encryption is enforced by the cloud/workspace layer (cloud provider
default or customer-managed keys) and is NOT directly visible in workspace
system tables.  A note evidence records this limitation; the LLM judge weighs
the governance-proxy signals and is expected to return low/medium confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_EXT_LOCATIONS_SQL = (
    "SELECT COUNT(*) AS external_location_count"
    " FROM system.information_schema.external_locations"
)

_STORAGE_CREDS_SQL = (
    "SELECT COUNT(*) AS storage_credential_count"
    " FROM system.information_schema.storage_credentials"
)

_TABLE_TYPE_SQL = (
    "SELECT COUNT(*) AS total_tables,"
    " SUM(CASE WHEN table_type = 'EXTERNAL' THEN 1 ELSE 0 END) AS external_tables"
    " FROM system.information_schema.tables"
    " WHERE table_type IN ('MANAGED', 'EXTERNAL')"
    " AND table_catalog <> 'hive_metastore'"
)

_GRANT_BREADTH_SQL = (
    "SELECT COUNT(*) AS total_grants,"
    " SUM(CASE WHEN grantee = 'account users'"
    "          OR grantee ILIKE '%PUBLIC%' THEN 1 ELSE 0 END) AS broad_grants"
    " FROM system.information_schema.table_privileges"
    " WHERE table_catalog <> 'hive_metastore'"
)

_ENCRYPTION_NOTE = (
    "At-rest encryption for Databricks storage is enforced at the cloud/workspace level "
    "(cloud provider default encryption or customer-managed keys) and is NOT visible via "
    "the agent's service principal in workspace system tables. This check assesses the "
    "access-governance proxy (external location / credential governance, grant breadth) as "
    "the observable signal. Admin confirmation is required to verify actual encryption "
    "posture."
)

_REF = "https://docs.databricks.com/en/security/encryption/index.html"


@register(layer="storage", question_ids=["STO-SCP-01"])
class EncryptionAccessCheck(Check):
    """Assess encryption and access control on stored data.

    Evidence is gathered from:
    - ``system.information_schema.external_locations`` (governed cloud paths)
    - ``system.information_schema.storage_credentials`` (credential registration)
    - ``system.information_schema.tables`` (external vs managed table share)
    - ``system.information_schema.table_privileges`` (broad/public grant breadth)

    A note records that at-rest encryption is not observable from system tables
    and requires admin confirmation. The LLM judge weighs the governance
    proxy signals.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        ext_rows = ctx.sql.query(_EXT_LOCATIONS_SQL)
        cred_rows = ctx.sql.query(_STORAGE_CREDS_SQL)
        table_rows = ctx.sql.query(_TABLE_TYPE_SQL)
        grant_rows = ctx.sql.query(_GRANT_BREADTH_SQL)

        ext_count = int((ext_rows[0].get("external_location_count") or 0) if ext_rows else 0)
        cred_count = int(
            (cred_rows[0].get("storage_credential_count") or 0) if cred_rows else 0
        )
        total_tables = int((table_rows[0].get("total_tables") or 0) if table_rows else 0)
        external_tables = int((table_rows[0].get("external_tables") or 0) if table_rows else 0)
        total_grants = int((grant_rows[0].get("total_grants") or 0) if grant_rows else 0)
        broad_grants = int((grant_rows[0].get("broad_grants") or 0) if grant_rows else 0)

        ext_pct = (
            round(100.0 * external_tables / total_tables, 1) if total_tables > 0 else 0.0
        )
        broad_pct = round(100.0 * broad_grants / total_grants, 1) if total_grants > 0 else 0.0

        gov_evidence = Evidence(
            kind="sql",
            summary=(
                f"{ext_count} external location(s) and {cred_count} storage credential(s) "
                "registered in Unity Catalog; "
                f"{external_tables} of {total_tables} UC tables are EXTERNAL "
                f"({ext_pct}%), backed by governed cloud paths"
            ),
            detail=(
                _EXT_LOCATIONS_SQL + " ; " + _STORAGE_CREDS_SQL + " ; " + _TABLE_TYPE_SQL
            ),
            rows=(ext_rows[:5] + cred_rows[:5] + table_rows[:3]),
            ref=_REF,
        )
        grant_evidence = Evidence(
            kind="sql",
            summary=(
                f"{total_grants} total table grant(s); {broad_grants} broad/public grant(s) "
                f"({broad_pct}% of total) — high broad_grants indicates over-permissive access"
            ),
            detail=_GRANT_BREADTH_SQL,
            rows=grant_rows[:5],
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_ENCRYPTION_NOTE,
            rows=[],
            ref=_REF,
        )
        return [gov_evidence, grant_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
