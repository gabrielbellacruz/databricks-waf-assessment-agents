"""Compute user-isolation check (LLM-judged).

Answers:
  PRO-SCP-02  Use compute that supports user isolation

Signal: cluster access-mode (data_security_mode) distribution from
system.compute.clusters. Clusters configured with SINGLE_USER or USER_ISOLATION
access mode provide user-level isolation; clusters with LEGACY or null access mode
do not enforce user isolation. The LLM judge weighs the cluster distribution
against the principle that transformation jobs should run on compute that enforces
row/column-level security and user isolation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = (
    "SELECT data_security_mode, COUNT(*) AS cluster_count "
    "FROM system.compute.clusters "
    "WHERE delete_time IS NULL "
    "GROUP BY data_security_mode "
    "ORDER BY cluster_count DESC"
)

_NOTE = (
    "Cluster data_security_mode indicates whether user isolation is enforced: "
    "SINGLE_USER provides per-user cluster isolation; USER_ISOLATION (shared) enforces "
    "Unity Catalog row/column-level security. LEGACY or null clusters do not enforce user "
    "isolation. The agent can only observe active cluster configurations, not per-job "
    "compute assignments — manual confirmation is needed to verify that transformation jobs "
    "are consistently routed to isolated compute."
)

_REF = "https://docs.databricks.com/en/compute/configure.html#access-mode"


@register(layer="processing", question_ids=["PRO-SCP-02"])
class ComputeIsolationCheck(Check):
    """Assess user-isolation posture of transformation compute.

    Queries system.compute.clusters for data_security_mode distribution.
    A note explains what each mode implies for user isolation and records
    that per-job compute assignment is not observable from system tables.
    The LLM judge weighs the proportion of isolated vs unrestricted clusters.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            isolated = sum(
                int(r.get("cluster_count") or 0)
                for r in rows
                if str(r.get("data_security_mode") or "").upper()
                in ("SINGLE_USER", "USER_ISOLATION")
            )
            total = sum(int(r.get("cluster_count") or 0) for r in rows)
            pct = round(100.0 * isolated / total, 1) if total > 0 else 0.0
            summary = (
                f"{isolated} of {total} active cluster(s) use SINGLE_USER or "
                f"USER_ISOLATION access mode ({pct}%)"
            )
        else:
            summary = "No active clusters found in system.compute.clusters"

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=rows[:10],
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )
        return [sql_evidence, note_evidence]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
