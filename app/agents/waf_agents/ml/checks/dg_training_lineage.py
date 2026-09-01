"""Training-data-to-model lineage check (LLM-judged).

Answers:
  ML-DG-02  Track lineage from training data to model

Signals:
  * ``system.access.table_lineage`` — count of ML-suggestive tables (schemas or names
    containing feature*, model*, ml*, train*) that appear as lineage targets in the last
    90 days, plus a sample of upstream-source → ML-target edges. Presence indicates that
    at least some data-to-model lineage events are being recorded by Unity Catalog.
  * Note: MLflow experiment lineage (model version → experiment run → training dataset)
    is not captured in system.access.table_lineage for all configurations. The signal here
    reflects table-level lineage (e.g. feature table writes) but does not cover MLflow
    Run → RegisteredModel provenance chains.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 90

# Count ML-suggestive tables appearing as lineage targets in the window.
_ML_TARGETS_SQL = (
    "SELECT COUNT(DISTINCT target_table_full_name) AS ml_lineage_targets "
    "FROM system.access.table_lineage "
    f"WHERE event_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS "
    "  AND (LOWER(target_table_full_name) LIKE '%feature%' "
    "       OR LOWER(target_table_full_name) LIKE '%model%' "
    "       OR LOWER(target_table_full_name) LIKE '%ml%' "
    "       OR LOWER(target_table_full_name) LIKE '%train%')"
)

# Sample upstream-source → ML-target lineage edges.
_ML_EDGES_SQL = (
    "SELECT source_table_full_name, target_table_full_name, COUNT(*) AS edge_events "
    "FROM system.access.table_lineage "
    f"WHERE event_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS "
    "  AND (LOWER(target_table_full_name) LIKE '%feature%' "
    "       OR LOWER(target_table_full_name) LIKE '%model%' "
    "       OR LOWER(target_table_full_name) LIKE '%ml%') "
    "  AND source_table_full_name IS NOT NULL "
    "GROUP BY source_table_full_name, target_table_full_name "
    "ORDER BY edge_events DESC "
    "LIMIT 10"
)

_NOTE = (
    f"system.access.table_lineage captures Unity Catalog table-level lineage events within "
    f"the last {_WINDOW_DAYS} days. MLflow experiment lineage (model version → experiment run "
    "→ dataset) and notebook-level dataset references are NOT captured here, so a workspace "
    "that trains models from notebooks without writing intermediate UC tables will appear as "
    "not having lineage even if MLflow records provenance internally."
)

_REF = "https://docs.databricks.com/en/data-governance/unity-catalog/data-lineage.html"


@register(layer="ml", question_ids=["ML-DG-02"])
class MlTrainingLineageCheck(Check):
    """LLM-judged check for ML-DG-02: lineage from training data to model."""

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        target_rows = ctx.sql.query(_ML_TARGETS_SQL)
        edge_rows = ctx.sql.query(_ML_EDGES_SQL)

        ml_targets = int(
            (target_rows[0].get("ml_lineage_targets") or 0) if target_rows else 0
        )

        lineage_evidence = Evidence(
            kind="sql",
            summary=(
                f"{ml_targets} ML-suggestive tables appear as lineage targets "
                f"in system.access.table_lineage (last {_WINDOW_DAYS} days)"
            ),
            detail=_ML_TARGETS_SQL,
            rows=[{"ml_lineage_targets": ml_targets}],
            ref=_REF,
        )
        edge_evidence = Evidence(
            kind="sql",
            summary=(
                f"{len(edge_rows)} distinct source→ML-target lineage edges observed "
                f"(top-10 by event count shown)"
            ),
            detail=_ML_EDGES_SQL,
            rows=edge_rows[:10],
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )
        return [lineage_evidence, edge_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
