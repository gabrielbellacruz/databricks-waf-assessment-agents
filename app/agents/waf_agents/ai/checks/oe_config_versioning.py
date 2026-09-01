"""AI config versioning check (LLM-judged).

Answers:
  AI-OE-04  Version prompts, models, and app configs together

Signals:
1. ``system.access.audit``: model-serving endpoint create/update events from the
   last 30 days.  Frequency of endpoint updates suggests active iteration;
   endpoint names that contain version tokens (v1, v2, -prod, -staging) suggest
   a versioning convention.
2. ``system.serving.endpoint_usage``: distinct endpoint names queried — names
   with version-style suffixes (v1, v2, -20xx) are a proxy for versioned configs.

Limitations noted:
- Prompt versioning (storing prompt templates in MLflow, source control, or a
  prompt registry) is NOT observable from system tables.
- App config versioning (Databricks Apps, DABs bundles) is not directly
  observable from audit events alone.
- Endpoint-name conventions are heuristic only; teams may use other schemes.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_ENDPOINT_UPDATES_SQL = """\
SELECT action_name,
       COUNT(*) AS event_count
FROM system.access.audit
WHERE service_name IN ('serving', 'mlflowEndpoints', 'mlflowAcledArtifact')
  AND action_name IN (
      'createServingEndpoint', 'updateServingEndpoint',
      'deleteServingEndpoint', 'createEndpoint', 'updateEndpoint'
  )
  AND event_date >= current_date() - INTERVAL 30 DAYS
GROUP BY action_name
ORDER BY event_count DESC\
"""

_ENDPOINT_NAMES_SQL = """\
SELECT DISTINCT endpoint_name
FROM system.serving.endpoint_usage
WHERE window_start_time >= current_timestamp() - INTERVAL 30 DAYS
ORDER BY endpoint_name
LIMIT 30\
"""

_NOTE = (
    "Prompt versioning (storing prompts in MLflow Prompt Registry, source control, or "
    "a dedicated template store) is NOT observable from Databricks system tables. "
    "Endpoint create/update audit events confirm that model configurations change over "
    "time but do not confirm that prompts, models, and app configs are versioned "
    "together as a unit. Endpoint-name version tokens (v1, v2, -prod) are a heuristic "
    "proxy only. A reviewer must confirm whether a unified versioning and promotion "
    "workflow exists."
)

_REF = "https://docs.databricks.com/en/mlflow/prompt-engineering.html"


@register(layer="ai", question_ids=["AI-OE-04"])
class ConfigVersioningCheck(Check):
    """Assess versioning discipline for AI configs via endpoint update events and names.

    Evidence:
    - system.access.audit: frequency and types of serving endpoint mutations.
    - system.serving.endpoint_usage: endpoint names for version-token heuristics.
    A note records that prompt and app-config versioning are not observable.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        update_rows = ctx.sql.query(_ENDPOINT_UPDATES_SQL)
        name_rows = ctx.sql.query(_ENDPOINT_NAMES_SQL)

        total_update_events = sum(int(r.get("event_count") or 0) for r in update_rows)
        if total_update_events > 0:
            update_summary = (
                f"{total_update_events} model-serving endpoint create/update/delete "
                f"event(s) across {len(update_rows)} distinct action type(s) "
                "in the last 30 days (system.access.audit)"
            )
        else:
            update_summary = (
                "No serving endpoint create/update/delete events found "
                "in system.access.audit for the last 30 days"
            )

        update_evidence = Evidence(
            kind="sql",
            summary=update_summary,
            detail=_ENDPOINT_UPDATES_SQL,
            rows=update_rows,
            ref="https://docs.databricks.com/en/admin/system-tables/audit.html",
        )

        endpoint_names = [r.get("endpoint_name", "") for r in name_rows]
        _version_tokens = ["v1", "v2", "v3", "-prod", "-dev", "-staging", "2024", "2025", "2026"]
        versioned_count = sum(
            1 for n in endpoint_names
            if any(tok in str(n).lower() for tok in _version_tokens)
        )
        if endpoint_names:
            name_summary = (
                f"{len(endpoint_names)} distinct endpoint name(s) in use; "
                f"{versioned_count} appear to use a version/env token "
                "(v1, v2, -prod, -staging, year) as a naming heuristic"
            )
        else:
            name_summary = "No endpoint names found in system.serving.endpoint_usage"

        name_evidence = Evidence(
            kind="sql",
            summary=name_summary,
            detail=_ENDPOINT_NAMES_SQL,
            rows=[{"endpoint_name": n} for n in endpoint_names[:30]],
            ref="https://docs.databricks.com/en/admin/system-tables/serving.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [update_evidence, name_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
