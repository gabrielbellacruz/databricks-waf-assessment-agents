"""Unity Catalog governance of AI assets (LLM-judged).

Answers:
  AI-DG-01  Govern AI assets alongside data in Unity Catalog

Signal:
  1. system.information_schema.routines — UC-registered functions and tools.
  2. system.serving.endpoint_usage — distinct serving endpoints requested in the
     last 30 days (presence check; may be absent/empty).

Limitation notes are included because UC registered models (ML models) are not
exposed through information_schema.routines or information_schema.tables in all
Databricks versions; the SP cannot enumerate them via system tables alone. The
LLM judge weighs the available evidence and returns unknown/low when signals
are absent.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_ROUTINES_SQL = (
    "SELECT COUNT(*) AS uc_routines,"
    " COUNT(DISTINCT routine_catalog) AS routine_catalogs"
    " FROM system.information_schema.routines"
    " WHERE routine_catalog <> 'hive_metastore'"
)

_ENDPOINTS_SQL = (
    "SELECT COUNT(DISTINCT endpoint_name) AS uc_asset_endpoints"
    " FROM system.serving.endpoint_usage"
    " WHERE CAST(window_start_time AS DATE) >= CURRENT_DATE - INTERVAL 30 DAYS"
)

_REF = "https://docs.databricks.com/en/machine-learning/manage-model-lifecycle/index.html"

_MODEL_LIMITATION = (
    "UC registered models (MLflow Model Registry in Unity Catalog) are not exposed"
    " through system.information_schema.routines or .tables in all Databricks"
    " versions; this check cannot enumerate them via system tables alone."
    " Verify model governance via the Unity Catalog UI or Models REST API."
)

_ENDPOINT_LIMITATION = (
    "system.serving.endpoint_usage may be absent or empty in workspaces where"
    " Model Serving is not in use or the table is not yet populated."
)


@register(layer="ai", question_ids=["AI-DG-01"])
class UcAiAssetsCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        routine_rows = ctx.sql.query(_ROUTINES_SQL)
        endpoint_rows = ctx.sql.query(_ENDPOINTS_SQL)

        r = routine_rows[0] if routine_rows else {}
        uc_routines = int(r.get("uc_routines") or 0)
        routine_catalogs = int(r.get("routine_catalogs") or 0)

        e = endpoint_rows[0] if endpoint_rows else {}
        endpoint_count = int(e.get("uc_asset_endpoints") or 0)

        routine_evidence = Evidence(
            kind="sql",
            summary=(
                f"{uc_routines} UC-registered function(s)/tool(s) across"
                f" {routine_catalogs} catalog(s) found in information_schema.routines"
            ),
            detail=_ROUTINES_SQL,
            rows=[{"uc_routines": uc_routines, "routine_catalogs": routine_catalogs}],
            ref=_REF,
        )
        endpoint_evidence = Evidence(
            kind="sql",
            summary=(
                f"{endpoint_count} distinct serving endpoint(s) active in the last"
                " 30 days (from system.serving.endpoint_usage)"
            ),
            detail=_ENDPOINTS_SQL,
            rows=[{"uc_asset_endpoints": endpoint_count}],
            ref=_REF,
        )
        model_limitation = Evidence(
            kind="uc_metadata",
            summary=_MODEL_LIMITATION,
            detail=_ENDPOINT_LIMITATION,
            ref=_REF,
        )
        return [routine_evidence, endpoint_evidence, model_limitation]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
