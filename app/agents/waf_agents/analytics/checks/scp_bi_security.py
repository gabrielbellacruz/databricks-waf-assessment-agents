"""BI connection and shared-results security check (LLM-judged).

Answers:
  ANA-SCP-05  Secure BI connections and shared results

Whether BI connections are encrypted and shared results are governed is not
directly observable from system tables. The observable proxies are:
  * system.compute.warehouses — channel type (serverless/pro enforce TLS;
    classic warehouses depend on network configuration)
  * system.access.audit — Delta Sharing events (createShare, updateShare,
    addShareRecipient) that indicate how results are being shared externally

A note records that external BI connection settings and result-export governance
require manual confirmation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WAREHOUSE_SQL = (
    "SELECT channel, COUNT(*) AS warehouse_count "
    "FROM system.compute.warehouses "
    "GROUP BY channel"
)

_SHARE_EVENTS_SQL = """\
SELECT action_name, COUNT(*) AS event_count
FROM system.access.audit
WHERE event_time >= current_timestamp() - INTERVAL 30 DAYS
  AND action_name IN (
        'createShare', 'updateShare', 'deleteShare',
        'addShareRecipient', 'removeShareRecipient'
  )
GROUP BY action_name\
"""

# Channel values that enforce encrypted connections from Databricks documentation.
_ENCRYPTED_CHANNELS = frozenset(
    {
        "CHANNEL_NAME_SERVERLESS",
        "CHANNEL_NAME_PRO",
        "SERVERLESS",
        "PRO",
        "PREVIEW",
    }
)

_NOTE = (
    "BI client connection encryption depends on the warehouse type: serverless and pro "
    "warehouses enforce TLS; classic warehouses rely on network configuration. "
    "Whether external BI tools (Tableau, Power BI, etc.) are configured with encrypted "
    "connections and whether shared results carry row-level security, expiry, or governance "
    "controls cannot be observed from system tables alone. Manual confirmation is required."
)

_REF = "https://docs.databricks.com/en/sql/admin/sql-endpoints.html"


@register(layer="analytics", question_ids=["ANA-SCP-05"])
class BiSecurityCheck(Check):
    """Assess BI connection security via warehouse channel type and sharing events.

    Evidence is gathered from system.compute.warehouses and system.access.audit.
    A note records what cannot be observed and requires manual confirmation.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        wh_rows = ctx.sql.query(_WAREHOUSE_SQL)

        total_wh = sum(int(r.get("warehouse_count") or 0) for r in wh_rows)
        encrypted_wh = sum(
            int(r.get("warehouse_count") or 0)
            for r in wh_rows
            if str(r.get("channel") or "").upper() in _ENCRYPTED_CHANNELS
        )

        if total_wh > 0:
            enc_pct = round(100.0 * encrypted_wh / total_wh, 1)
            wh_summary = (
                f"{encrypted_wh} of {total_wh} warehouses use serverless/pro channel "
                f"(TLS enforced) — {enc_pct}%"
            )
        else:
            wh_summary = "No warehouses found in system.compute.warehouses"

        share_rows = ctx.sql.query(_SHARE_EVENTS_SQL)
        share_total = sum(int(r.get("event_count") or 0) for r in share_rows)
        share_summary = (
            f"{share_total} sharing-related audit event(s) in the last 30 days"
            if share_total > 0
            else "No sharing events found in system.access.audit for the last 30 days"
        )

        return [
            Evidence(
                kind="sql",
                summary=wh_summary,
                detail=_WAREHOUSE_SQL,
                rows=wh_rows,
                ref="https://docs.databricks.com/en/sql/admin/create-sql-warehouse.html",
            ),
            Evidence(
                kind="sql",
                summary=share_summary,
                detail=_SHARE_EVENTS_SQL,
                rows=share_rows,
                ref="https://docs.databricks.com/en/delta-sharing/index.html",
            ),
            Evidence(
                kind="note",
                summary=_NOTE,
                rows=[],
                ref=_REF,
            ),
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
