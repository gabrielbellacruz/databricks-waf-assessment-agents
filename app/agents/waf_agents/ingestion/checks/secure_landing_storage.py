"""Secure landing cloud storage check (LLM-judged).

Answers:
  ING-SCP-02  Secure access to landing cloud storage

Signal: landing storage is governed through Unity Catalog external locations
(with named storage credentials) rather than open/ad-hoc access. The check
queries ``system.information_schema.external_locations`` for the total count
of governed locations, how many are backed by TLS-encrypted cloud paths
(abfss, s3, gs, wasbs), and how many are associated with a named storage
credential. The mere existence of governed external locations indicates that
landing storage is managed through Unity Catalog rather than ad-hoc access.

If ``external_locations`` is not queryable the check falls back to counting
EXTERNAL tables in ``information_schema.tables`` as a weaker proxy for cloud
storage use, and passes that evidence to the LLM judge.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
    COUNT(*) AS total_locations,
    SUM(CASE
        WHEN url ILIKE 'abfss:%' OR url ILIKE 's3:%'
             OR url ILIKE 'gs:%' OR url ILIKE 'wasbs:%'
        THEN 1 ELSE 0 END) AS tls_backed,
    SUM(CASE
        WHEN storage_credential_name IS NOT NULL
             AND storage_credential_name <> ''
        THEN 1 ELSE 0 END) AS credential_backed
FROM system.information_schema.external_locations"""

_FALLBACK_SQL = """\
SELECT COUNT(*) AS external_table_count
FROM system.information_schema.tables
WHERE table_type = 'EXTERNAL'"""

_REF = "https://docs.databricks.com/en/connect/unity-catalog/external-locations.html"


@register(layer="ingestion", question_ids=["ING-SCP-02"])
class SecureLandingStorageCheck(Check):
    """Check whether landing-zone cloud storage is secured via Unity Catalog
    external locations backed by named storage credentials."""

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        if rows:
            row = rows[0]
            total = int(row.get("total_locations") or 0)
            tls = int(row.get("tls_backed") or 0)
            raw_cred = row.get("credential_backed")
            cred_count = int(raw_cred) if raw_cred is not None else None

            cred_part = (
                f"; {cred_count} backed by a named storage credential"
                if cred_count is not None
                else ""
            )
            summary = (
                f"{total} Unity Catalog external location(s) found"
                f"; {tls} use TLS-backed cloud paths"
                f"{cred_part}"
            )
            return [
                Evidence(
                    kind="sql",
                    summary=summary,
                    detail=_SQL,
                    rows=[{
                        "total_locations": total,
                        "tls_backed": tls,
                        "credential_backed": cred_count,
                    }],
                    ref=_REF,
                )
            ]

        # Fall back: count EXTERNAL tables as a weaker cloud-storage proxy.
        fb_rows = ctx.sql.query(_FALLBACK_SQL)
        fb_count = int((fb_rows[0].get("external_table_count") or 0) if fb_rows else 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    "external_locations table not queryable; "
                    f"{fb_count} EXTERNAL table(s) found as a cloud-storage proxy"
                ),
                detail=_FALLBACK_SQL,
                rows=[{"external_table_count": fb_count}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
