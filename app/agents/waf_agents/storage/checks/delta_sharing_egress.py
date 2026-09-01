"""Delta Sharing egress cost monitoring check (LLM-judged).

Answers:
  STO-CO-05  Monitor Delta Sharing egress costs

Signal:
  1. Billing usage records for network / egress / sharing-related SKUs
     (sku_name ILIKE '%NETWORK%' OR ILIKE '%EGRESS%' OR ILIKE '%SHARING%') in the
     last 90 days, grouped by SKU name. A non-empty result indicates egress-relevant
     spend is visible in billing; the SKU breakdown helps identify Delta Sharing-
     specific lines if they exist.
  2. Count of DELTASHARING-format tables in system.information_schema.tables as
     evidence that Delta Sharing is actively in use (shared tables have been created).

Note: fine-grained per-recipient egress attribution is not exposed in
system.billing.usage. If Delta Sharing egress is bundled under a generic network
SKU it cannot be separated programmatically. A reviewer may need to inspect the Delta
Sharing audit log or cloud-provider billing for a complete picture.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 90

_SQL_EGRESS_SKUS = (
    "SELECT sku_name, COUNT(*) AS records, SUM(usage_quantity) AS total_usage "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "AND (sku_name ILIKE '%NETWORK%' OR sku_name ILIKE '%EGRESS%' OR sku_name ILIKE '%SHARING%') "
    "GROUP BY sku_name "
    "ORDER BY total_usage DESC "
    "LIMIT 20"
)

_SQL_SHARING_TABLES = (
    "SELECT COUNT(*) AS deltasharing_tables "
    "FROM system.information_schema.tables "
    "WHERE data_source_format = 'DELTASHARING' "
    "AND table_catalog <> 'hive_metastore'"
)

_NOTE_LIMIT = (
    "Fine-grained per-recipient egress attribution for Delta Sharing is not available in "
    "system.billing.usage; only SKU-level aggregates are visible. Delta Sharing egress may "
    "appear bundled under a generic network SKU, making it impossible to isolate "
    "programmatically. A reviewer should verify egress monitoring via the Delta Sharing audit log "
    "or cloud-provider billing where per-recipient detail is needed."
)

_REF = "https://docs.databricks.com/en/delta-sharing/index.html"


@register(layer="storage", question_ids=["STO-CO-05"])
class DeltaSharingEgressCheck(Check):
    """Assess whether Delta Sharing egress costs are monitored.

    Two SQL signals are gathered: egress / network / sharing SKUs from billing.usage
    and DELTASHARING-format tables from information_schema. A note records the
    per-recipient attribution limitation. The LLM judge is expected to lean toward
    low confidence when Delta Sharing tables are absent (sharing may not be in use).
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        egress_rows = ctx.sql.query(_SQL_EGRESS_SKUS)
        sharing_rows = ctx.sql.query(_SQL_SHARING_TABLES)

        sharing_tables = int(
            (sharing_rows[0].get("deltasharing_tables") or 0) if sharing_rows else 0
        )
        sku_count = len(egress_rows)
        total_egress_records = sum(int(r.get("records") or 0) for r in egress_rows)

        egress_evidence = Evidence(
            kind="sql",
            summary=(
                f"{sku_count} network/egress/sharing SKU(s) found in billing.usage "
                f"over the last {_WINDOW_DAYS} days "
                f"({total_egress_records} total billing record(s))"
            ),
            detail=_SQL_EGRESS_SKUS,
            rows=egress_rows[:20],
            ref=_REF,
        )
        sharing_evidence = Evidence(
            kind="sql",
            summary=(
                f"{sharing_tables} DELTASHARING-format table(s) found in "
                "system.information_schema.tables "
                "(evidence that Delta Sharing is actively in use)"
            ),
            detail=_SQL_SHARING_TABLES,
            rows=[{"deltasharing_tables": sharing_tables}],
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_NOTE_LIMIT,
            ref=_REF,
        )
        return [egress_evidence, sharing_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
