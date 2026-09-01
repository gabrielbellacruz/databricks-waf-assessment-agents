"""Secure sharing of stored data check (LLM-judged).

Answers:
  STO-IU-02  Enable secure sharing of stored data

Signal: Delta Sharing usage detected from ``system.information_schema.tables``
where ``data_source_format = 'DELTASHARING'`` (consumer-side signal: tables the
workspace consumes from a share). A limitation note is included because
provider-side share objects (shares, recipients, share permissions) are not
exposed through information_schema — that signal is not available to the SP.
The LLM judge weighs the consumer-side evidence to decide whether secure sharing
is in use vs copying data ad-hoc.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SHARING_TABLES_SQL = (
    "SELECT COUNT(*) AS sharing_tables,"
    " COUNT(DISTINCT table_catalog) AS sharing_catalogs"
    " FROM system.information_schema.tables"
    " WHERE data_source_format = 'DELTASHARING'"
    " AND table_catalog <> 'hive_metastore'"
)

_REF = "https://docs.databricks.com/en/data-sharing/index.html"

_PROVIDER_LIMITATION = (
    "Provider-side Delta Sharing objects (shares, recipients, share permissions)"
    " are not exposed through system.information_schema and are not visible to the"
    " SP's system-table queries. Consumer-side signal only."
)


@register(layer="storage", question_ids=["STO-IU-02"])
class SecureSharingCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SHARING_TABLES_SQL)
        row = rows[0] if rows else {}
        sharing_tables = int(row.get("sharing_tables") or 0)
        sharing_catalogs = int(row.get("sharing_catalogs") or 0)

        consumer_evidence = Evidence(
            kind="sql",
            summary=(
                f"{sharing_tables} DELTASHARING consumer table(s) found"
                f" across {sharing_catalogs} catalog(s)"
            ),
            detail=_SHARING_TABLES_SQL,
            rows=rows[:10],
            ref=_REF,
        )
        limitation_evidence = Evidence(
            kind="uc_metadata",
            summary=_PROVIDER_LIMITATION,
            detail=(
                "To assess provider-side sharing, review Delta Sharing shares and"
                " recipients via the Databricks UI or SHOW SHARES / SHOW RECIPIENTS SQL."
            ),
            ref=_REF,
        )
        return [consumer_evidence, limitation_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
