"""Encrypt data in transit from source systems check (LLM-judged).

Answers:
  ING-SCP-03  Encrypt data in transit from source systems

Signal (thin): external-location URL schemes indicate TLS-capable cloud
storage transports. The query counts total external locations, how many use
TLS-backed schemes (abfss, s3, gs, wasbs), and how many use insecure schemes
(http, ftp, wasb). A second note evidence records that Databricks control- and
data-plane traffic is TLS by default but that source-to-landing transfer
encryption (e.g. JDBC/SFTP) is not observable via system tables. The LLM judge
weighs both pieces and produces a verdict for manual review.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT COUNT(*) AS total_locations,
       SUM(CASE WHEN url ILIKE 'abfss:%' OR url ILIKE 's3:%'
                    OR url ILIKE 'gs:%'  OR url ILIKE 'wasbs:%'
               THEN 1 ELSE 0 END) AS tls_scheme,
       SUM(CASE WHEN url ILIKE 'http:%' OR url ILIKE 'ftp:%'
                    OR url ILIKE 'wasb:%'
               THEN 1 ELSE 0 END) AS insecure_scheme
FROM system.information_schema.external_locations"""

_NOTE = (
    "Databricks control- and data-plane traffic is TLS by default; whether "
    "*source-to-landing* transfers (e.g. JDBC/SFTP from source systems) enforce "
    "encryption is not observable in system tables. This check only inspects "
    "external-location URL schemes as a partial proxy — manual confirmation needed."
)

_REF = "https://docs.databricks.com/en/security/network/index.html"


@register(layer="ingestion", question_ids=["ING-SCP-03"])
class EncryptInTransitCheck(Check):
    """Check whether data in transit from source systems is encrypted.

    Evidence is gathered from ``system.information_schema.external_locations``
    (URL scheme analysis) plus a note explaining that source-to-landing
    encryption is not fully observable via system tables. The LLM judge weighs
    both pieces and produces a verdict capped at medium confidence.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            total = int(row.get("total_locations") or 0)
            tls = int(row.get("tls_scheme") or 0)
            insecure = int(row.get("insecure_scheme") or 0)
        else:
            total = 0
            tls = 0
            insecure = 0

        summary = (
            f"{total} external location(s) found"
            f"; {tls} use TLS-backed URL schemes"
            f"; {insecure} use insecure URL schemes (http/ftp/wasb)"
        )

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[{"total_locations": total, "tls_scheme": tls, "insecure_scheme": insecure}],
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
