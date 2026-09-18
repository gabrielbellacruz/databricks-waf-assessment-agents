"""Model rollback capability check (LLM-judged).

Answers:
  ML-R-04  Enable rollback to a previous model version

Rolling back a deployed model to a known-good version requires the model
registry (MLflow or Unity Catalog) to hold multiple versioned artifacts.
``system.serving.served_entities`` exposes the custom models served on
endpoints and their versions; models with more than one served version are
the ones that can actually be rolled back to a previous version.
``system.access.audit`` records model-lifecycle events (model version
registrations, transitions, alias assignments) but may also be restricted.
Both queries are attempted; a strong limitation note records what cannot
be inferred: whether the currently-deployed alias points at a tested,
production-ready version, and whether rollback run-books or automation
exist.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

# Distinct needle: "registerModelVersion"
_AUDIT_SQL = """\
SELECT
  action_name,
  COUNT(*) AS event_count
FROM system.access.audit
WHERE event_time >= current_timestamp() - INTERVAL 90 DAYS
  AND action_name IN (
    'registerModelVersion',
    'transitionModelVersionStage',
    'setRegisteredModelAlias',
    'deleteModelVersion'
  )
GROUP BY action_name
ORDER BY event_count DESC\
"""

# Distinct needle: "served_entities" model-version rollback signal
_MODELS_SQL = """\
SELECT
  COUNT(DISTINCT entity_name) AS registered_model_count,
  COUNT(DISTINCT CASE WHEN entity_version IS NOT NULL
                 THEN concat(entity_name, ':', entity_version) END) AS model_version_count
FROM system.serving.served_entities
WHERE entity_type = 'CUSTOM_MODEL'\
"""

_NOTE = (
    "Model rollback capability depends on having multiple versioned model artifacts "
    "registered in the Unity Catalog Model Registry or MLflow tracking server. "
    "The agent cannot inspect the actual model versions present, their aliases, or "
    "whether rollback run-books / CI gates exist. Audit event counts are only a weak "
    "proxy — manual review of the model registry and deployment workflow is required."
)

_REF = "https://docs.databricks.com/en/machine-learning/manage-model-lifecycle/index.html"


@register(layer="ml", question_ids=["ML-R-04"])
class MlModelRollbackCheck(Check):
    """Assess model rollback capability via audit events and model registry counts.

    Evidence is gathered from system.access.audit (last 90 days) for
    model-lifecycle events and from system.serving.served_entities for the
    count of served custom models and their versions (models with multiple
    versions are rollback-capable). A note evidence records that alias
    assignments and rollback procedures are not observable from system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        evidence: list[Evidence] = []

        # 1. Audit events for model lifecycle
        audit_rows = ctx.sql.query(_AUDIT_SQL)
        if audit_rows:
            total_events = sum(int(r.get("event_count") or 0) for r in audit_rows)
            action_names = [r.get("action_name", "") for r in audit_rows]
            audit_summary = (
                f"{total_events} model-lifecycle audit event(s) in the last 90 days "
                f"(actions: {', '.join(action_names)})"
            )
        else:
            total_events = 0
            audit_summary = (
                "No model-lifecycle audit events found in system.access.audit "
                "for the last 90 days (may indicate no model registry activity or "
                "insufficient SP permissions)"
            )

        evidence.append(
            Evidence(
                kind="sql",
                summary=audit_summary,
                detail=_AUDIT_SQL,
                rows=audit_rows,
                ref="https://docs.databricks.com/en/admin/system-tables/audit-logs.html",
            )
        )

        # 2. Served custom models and their versions (rollback signal)
        model_rows = ctx.sql.query(_MODELS_SQL)
        if model_rows:
            model_count = int(model_rows[0].get("registered_model_count") or 0)
            version_count = int(model_rows[0].get("model_version_count") or 0)
        else:
            model_count = version_count = 0

        if model_count > 0:
            model_summary = (
                f"{model_count} custom model(s) served across {version_count} "
                "version(s) (system.serving.served_entities); multiple versions per "
                "model enable rollback to a previous version"
            )
        else:
            model_summary = (
                "No custom models found in system.serving.served_entities "
                "(no served model endpoints, or insufficient SP access)"
            )

        evidence.append(
            Evidence(
                kind="sql",
                summary=model_summary,
                detail=_MODELS_SQL,
                rows=[{
                    "registered_model_count": model_count,
                    "model_version_count": version_count,
                }],
                ref=_REF,
            )
        )

        evidence.append(
            Evidence(
                kind="note",
                summary=_NOTE,
                rows=[],
                ref=_REF,
            )
        )

        return evidence

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
