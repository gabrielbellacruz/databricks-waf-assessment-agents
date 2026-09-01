"""Disaster-recovery pattern check (LLM-judged).

Answers:
  STO-R-03  Configure a disaster-recovery pattern for storage

True DR configuration (cross-region replication, backup policies, failover
targets) is not directly observable via the system tables available to this
agent.  Two weak proxy signals are collected:

1. CLONE usage in ``system.query.history`` — CLONE and DEEP CLONE statements
   are the primary Databricks-native mechanism for creating point-in-time
   table copies for backup/replication purposes.  High DEEP CLONE frequency
   suggests the team uses Delta-native backup.

2. Distinct catalog count in Unity Catalog — multiple catalogs (dev/staging/
   prod or primary/replica) provide a weak structural proxy for data
   partitioning that could support a DR topology.  A single catalog does NOT
   mean there is no DR, and multiple catalogs do NOT prove DR exists.

Both signals are indirect.  The LLM judge is expected to return 'unknown' or
'low' confidence in most cases and flag the need for manual verification.

NOTE: Cross-region replication, Geo-redundant storage accounts, and
infrastructure-level DR (backup vaults, replication rules) are not
observable via system.query.history or system.information_schema.  A reviewer
must verify these directly.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_CLONE_SQL = """\
SELECT
  SUM(CASE WHEN statement_text ILIKE '%DEEP CLONE%' THEN 1 ELSE 0 END) AS deep_clone_stmts,
  SUM(CASE WHEN statement_text ILIKE '%CLONE%' THEN 1 ELSE 0 END) AS clone_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 90 DAYS
  AND statement_text ILIKE '%CLONE%'"""

_CATALOGS_SQL = (
    "SELECT COUNT(DISTINCT catalog_name) AS catalog_count"
    " FROM system.information_schema.schemata"
    " WHERE catalog_name <> 'hive_metastore'"
)

_OBSERVABILITY_NOTE = (
    "NOTE: Cross-region replication, cloud-native backup vaults,"
    " and storage-account geo-redundancy settings are NOT observable"
    " via system.query.history or system.information_schema."
    " CLONE usage and catalog count are weak structural proxies only."
    " a reviewer must verify actual DR posture (RPO/RTO targets, backup schedules,"
    " and failover procedures) outside this automated check."
)

_REF = "https://docs.databricks.com/en/delta/clone.html"


@register(layer="storage", question_ids=["STO-R-03"])
class DisasterRecoveryCheck(Check):
    """Assess DR posture via CLONE usage and catalog-spread proxies.

    Direct DR observability is not available from system tables, so this check
    collects the closest available proxies and states the limitation
    explicitly.  The LLM judge is expected to lean toward ``unknown`` or
    ``partial`` with low confidence in almost all cases and to surface the
    observability gap in its rationale.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        clone_rows = ctx.sql.query(_CLONE_SQL)
        catalog_rows = ctx.sql.query(_CATALOGS_SQL)

        # --- CLONE usage signal ---
        clone_row = clone_rows[0] if clone_rows else {}
        deep_clone = int(clone_row.get("deep_clone_stmts") or 0)
        clone_total = int(clone_row.get("clone_stmts") or 0)
        shallow_clone = clone_total - deep_clone

        clone_evidence = Evidence(
            kind="sql",
            summary=(
                f"CLONE statements in the last 90 days:"
                f" DEEP CLONE={deep_clone},"
                f" SHALLOW CLONE={shallow_clone}"
                f" (total CLONE={clone_total})."
                " DEEP CLONE is the primary Delta backup/replication mechanism."
            ),
            detail=_CLONE_SQL,
            rows=[
                {
                    "deep_clone_stmts": deep_clone,
                    "clone_stmts": clone_total,
                }
            ],
            ref=_REF,
        )

        # --- Catalog count signal ---
        catalog_count = int(
            (catalog_rows[0].get("catalog_count") or 0) if catalog_rows else 0
        )
        catalog_evidence = Evidence(
            kind="sql",
            summary=(
                f"{catalog_count} distinct UC catalogs"
                " (excluding hive_metastore)."
                " Multiple catalogs may indicate environment separation"
                " or replica topology, but does not confirm DR configuration."
            ),
            detail=_CATALOGS_SQL,
            rows=catalog_rows[:5],
            ref=_REF,
        )

        observability_note = Evidence(
            kind="note",
            summary=_OBSERVABILITY_NOTE,
            rows=[],
            ref=_REF,
        )

        return [clone_evidence, catalog_evidence, observability_note]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
