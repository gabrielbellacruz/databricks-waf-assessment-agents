"""Model registry lifecycle management check (LLM-judged).

Answers:
  ML-OE-04  Use a model registry to manage the model lifecycle

Signals:
1. ``system.access.audit``: volume and diversity of model-registry actions
   (registerModel, createModelVersion, transitionModelVersionStage,
   setRegisteredModelAlias, deleteModelVersion, …) over the last 30 days.
   Presence of stage-transition or alias-set events is a strong proxy for
   active lifecycle management; only registration events without transitions
   suggests models are registered but not promoted.

2. ``system.information_schema.tables``: presence of tables in a
   ``models`` schema or catalog that indicate UC model registry usage.

Limitation: Unity Catalog model registry activity appears in audit logs
under ``unityCatalog`` or ``mlflow`` service names; the exact action names
vary by workspace version. Absence of registry events may mean the model
registry is unused *or* that audit events are filtered or delayed. A reviewer must
confirm whether UC or Workspace Model Registry is the canonical registry.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_REGISTRY_ACTIONS_SQL = """\
SELECT action_name,
       COUNT(*) AS event_count
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND (
    action_name ILIKE '%registeredModel%'
    OR action_name ILIKE '%modelVersion%'
    OR action_name ILIKE '%transitionModel%'
    OR action_name ILIKE '%setRegisteredModel%'
    OR action_name ILIKE '%deleteModel%'
    OR action_name IN (
      'registerModel', 'createRegisteredModel',
      'createModelVersion', 'transitionModelVersionStage',
      'deleteRegisteredModel', 'updateRegisteredModel'
    )
  )
GROUP BY action_name
ORDER BY event_count DESC
LIMIT 20\
"""

_UC_MODELS_SQL = """\
SELECT COUNT(*) AS total_models,
       COUNT(DISTINCT table_catalog) AS model_catalogs
FROM system.information_schema.tables
WHERE table_type = 'MANAGED'
  AND table_catalog <> 'hive_metastore'
  AND (
    table_schema ILIKE '%model%'
    OR table_name  ILIKE '%model%'
  )\
"""

_NOTE = (
    "Model registry audit events may appear under 'mlflow', 'mlflowAcl', or "
    "'unityCatalog' service_names depending on whether Workspace Model Registry or "
    "Unity Catalog model registry is in use. Absence of transition/alias events could "
    "mean models are registered but lifecycle stages are not managed, or that UC aliases "
    "(Champion/Challenger) are used instead of MLflow stages. A reviewer must confirm which "
    "registry is the canonical store and whether a promotion workflow "
    "(staging -> production) exists."
)

_REF = "https://docs.databricks.com/en/mlflow/model-registry.html"


@register(layer="ml", question_ids=["ML-OE-04"])
class ModelRegistryCheck(Check):
    """Assess model registry usage via audit events and UC information_schema.

    Evidence:
    - system.access.audit: volume and types of model registry actions.
    - system.information_schema.tables: UC tables in model-named schemas.
    A note records uncertainty about workspace vs UC registry and lifecycle
    stage management vs UC aliases.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        action_rows = ctx.sql.query(_REGISTRY_ACTIONS_SQL)
        uc_rows = ctx.sql.query(_UC_MODELS_SQL)

        total_events = sum(int(r.get("event_count") or 0) for r in action_rows)
        distinct_actions = len(action_rows)

        if total_events > 0:
            action_summary = (
                f"{total_events} model-registry audit event(s) across "
                f"{distinct_actions} distinct action type(s) in the last 30 days"
            )
        else:
            action_summary = (
                "No model-registry audit events found in system.access.audit "
                "for the last 30 days"
            )

        registry_evidence = Evidence(
            kind="sql",
            summary=action_summary,
            detail=_REGISTRY_ACTIONS_SQL,
            rows=action_rows[:20],
            ref=_REF,
        )

        u = uc_rows[0] if uc_rows else {}
        total_models = int(u.get("total_models") or 0)
        model_catalogs = int(u.get("model_catalogs") or 0)

        uc_summary = (
            f"{total_models} managed table(s) with 'model' in schema/name "
            f"across {model_catalogs} catalog(s) in Unity Catalog"
        )

        uc_evidence = Evidence(
            kind="sql",
            summary=uc_summary,
            detail=_UC_MODELS_SQL,
            rows=[{"total_models": total_models, "model_catalogs": model_catalogs}],
            ref="https://docs.databricks.com/en/machine-learning/manage-model-lifecycle/index.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [registry_evidence, uc_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
