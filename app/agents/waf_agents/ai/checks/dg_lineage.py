"""AI lineage tracking check (LLM-judged).

Answers:
  AI-DG-02  Track lineage from source data to AI outputs

Signal:
  1. system.access.audit — ML-lifecycle audit events (createModelVersion,
     logInputs, logOutputs, etc.) indicate that runs are being tracked.
  2. system.information_schema.routines — UC functions referencing data assets
     suggest that AI tooling is registered alongside its data dependencies.

Limitation note: End-to-end lineage from raw data tables → features → model
training run → endpoint inference is not fully captured in system tables. MLflow
experiment lineage requires mlflow API access (not available to the SP's
system-table queries). The LLM judge uses these proxy signals and should
return unknown/low when evidence is thin.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_AUDIT_SQL = (
    "SELECT COUNT(*) AS lineage_audit_events,"
    " COUNT(DISTINCT user_identity.email) AS distinct_users"
    " FROM system.access.audit"
    " WHERE action_name IN ("
    "  'createModelVersion','logInputs','logOutputs',"
    "  'registerModel','createRegisteredModel'"
    " )"
    " AND CAST(event_time AS DATE) >= CURRENT_DATE - INTERVAL 30 DAYS"
)

_ROUTINES_SQL = (
    "SELECT COUNT(*) AS lineage_routines,"
    " COUNT(DISTINCT routine_catalog) AS routine_catalogs"
    " FROM system.information_schema.routines"
    " WHERE routine_catalog <> 'hive_metastore'"
)

_REF = "https://docs.databricks.com/en/data-governance/unity-catalog/data-lineage.html"

_LINEAGE_LIMITATION = (
    "Full AI/ML lineage (raw data → features → training run → model → endpoint)"
    " is not captured in system.access.audit alone. MLflow experiment runs, logged"
    " inputs, and model-to-table links require MLflow tracking API queries, which"
    " are not accessible to the SP through system tables."
)


@register(layer="ai", question_ids=["AI-DG-02"])
class AiLineageCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        audit_rows = ctx.sql.query(_AUDIT_SQL)
        routine_rows = ctx.sql.query(_ROUTINES_SQL)

        a = audit_rows[0] if audit_rows else {}
        lineage_events = int(a.get("lineage_audit_events") or 0)
        distinct_users = int(a.get("distinct_users") or 0)

        r = routine_rows[0] if routine_rows else {}
        routines = int(r.get("lineage_routines") or 0)
        catalogs = int(r.get("routine_catalogs") or 0)

        audit_evidence = Evidence(
            kind="sql",
            summary=(
                f"{lineage_events} ML-lifecycle audit event(s) (createModelVersion,"
                f" logInputs, etc.) from {distinct_users} user(s) in the last 30 days"
            ),
            detail=_AUDIT_SQL,
            rows=[{"lineage_audit_events": lineage_events, "distinct_users": distinct_users}],
            ref=_REF,
        )
        routine_evidence = Evidence(
            kind="sql",
            summary=(
                f"{routines} UC-registered function(s)/tool(s) across {catalogs}"
                " catalog(s); these may define AI tools referencing data assets"
            ),
            detail=_ROUTINES_SQL,
            rows=[{"lineage_routines": routines, "routine_catalogs": catalogs}],
            ref=_REF,
        )
        limitation = Evidence(
            kind="uc_metadata",
            summary=_LINEAGE_LIMITATION,
            detail=(
                "Check MLflow experiment lineage via the Databricks UI or"
                " mlflow.get_run() / mlflow.MlflowClient().get_model_version_download_uri()."
            ),
            ref=_REF,
        )
        return [audit_evidence, routine_evidence, limitation]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
