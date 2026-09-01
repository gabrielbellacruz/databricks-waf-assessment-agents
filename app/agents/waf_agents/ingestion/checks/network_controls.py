"""Network controls check (LLM-judged).

Answers:
  ING-SCP-05  Apply network controls to ingestion connectivity

Network controls for ingestion (No-Public-IP, NCC, PrivateLink, Private Service
Connect, egress firewall, IP access lists) are configured at the
account/workspace-infrastructure level and are not visible in workspace system
tables.  The only observable proxy is the count of registered external locations,
which gives a rough surface-area signal for outbound data access. The LLM judge
weighs this thin signal with an explanatory note and is expected to return
``unknown`` or a ``low``-confidence verdict; admin confirmation is required to
assess the actual network posture.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = (
    "SELECT COUNT(*) AS external_locations "
    "FROM system.information_schema.external_locations"
)

_NETWORK_NOTE = (
    "Network controls for ingestion (No-Public-IP, NCC, PrivateLink/Private Service Connect, "
    "egress firewall, IP access lists) are configured at the account/workspace-infrastructure "
    "level and are not exposed in the system tables available to this agent. This check cannot "
    "verify them from platform data; it requires admin confirmation."
)

_NETWORK_REF = "https://docs.databricks.com/en/security/network/index.html"


@register(layer="ingestion", question_ids=["ING-SCP-05"])
class NetworkControlsCheck(Check):
    """Assess network controls applied to ingestion connectivity.

    Evidence is gathered from ``system.information_schema.external_locations``
    (the count of registered external locations gives a rough surface-area
    proxy). A dominant note evidence records that the actual network controls
    — No-Public-IP, NCC, PrivateLink/PSC, egress firewall, and IP access
    lists — are configured at the account/workspace-infrastructure level and
    are not exposed in workspace system tables; admin confirmation is
    required. The LLM judge is expected to return ``unknown`` or a
    ``low``-confidence verdict given the indirect evidence.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        count = int(rows[0].get("external_locations") or 0) if rows else 0

        sql_summary = (
            f"{count} external location(s) registered in "
            "system.information_schema.external_locations"
        )

        sql_evidence = Evidence(
            kind="sql",
            summary=sql_summary,
            detail=_SQL,
            rows=[{"external_locations": count}],
            ref=_NETWORK_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NETWORK_NOTE,
            rows=[],
            ref=_NETWORK_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
