"""Prompt and AI configuration governance check (LLM-judged).

Answers:
  AI-DG-05  Govern and version prompts and configurations

Signal:
  1. system.information_schema.routines — UC-registered Python/SQL functions
     whose routine_body or routine_definition mentions 'prompt', 'system_message',
     or 'template'; these suggest prompts are versioned as UC assets.
  2. system.access.audit — endpoint configuration-change events
     (updateServingEndpoint, editServingEndpoint) indicate that LLM config
     changes are being tracked in the audit log.

Limitation note: Prompts stored in notebooks, Repos, or external files are not
visible through system tables. Prompt versioning via MLflow prompt engineering
APIs is not exposed through system.information_schema. UC AI Prompt assets
(if used) may not appear in routines depending on the Databricks runtime version.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_ROUTINES_SQL = (
    "SELECT COUNT(*) AS prompt_func_count,"
    " COUNT(DISTINCT routine_catalog) AS routine_catalogs"
    " FROM system.information_schema.routines"
    " WHERE routine_catalog <> 'hive_metastore'"
    " AND ("
    "  LOWER(routine_definition) LIKE '%prompt%'"
    "  OR LOWER(routine_definition) LIKE '%system_message%'"
    "  OR LOWER(routine_definition) LIKE '%template%'"
    " )"
)

_AUDIT_SQL = (
    "SELECT COUNT(*) AS prompt_audit_events,"
    " COUNT(DISTINCT user_identity.email) AS distinct_users"
    " FROM system.access.audit"
    " WHERE action_name IN ("
    "  'updateServingEndpoint','editServingEndpoint',"
    "  'createServingEndpoint','deleteServingEndpoint'"
    " )"
    " AND CAST(event_time AS DATE) >= CURRENT_DATE - INTERVAL 30 DAYS"
)

_REF = (
    "https://docs.databricks.com/en/generative-ai/prompt-engineering/index.html"
)

_PROMPT_LIMITATION = (
    "Prompts stored in notebooks, Repos, or external files are not visible through"
    " system tables. MLflow prompt-engineering experiment tracking and UC Prompt"
    " asset registration may not appear in information_schema.routines depending on"
    " the Databricks runtime version. Audit events cover endpoint config changes but"
    " not prompt text versioning."
)


@register(layer="ai", question_ids=["AI-DG-05"])
class AiPromptGovernanceCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        routine_rows = ctx.sql.query(_ROUTINES_SQL)
        audit_rows = ctx.sql.query(_AUDIT_SQL)

        r = routine_rows[0] if routine_rows else {}
        prompt_funcs = int(r.get("prompt_func_count") or 0)
        routine_catalogs = int(r.get("routine_catalogs") or 0)

        a = audit_rows[0] if audit_rows else {}
        audit_events = int(a.get("prompt_audit_events") or 0)
        distinct_users = int(a.get("distinct_users") or 0)

        routine_evidence = Evidence(
            kind="sql",
            summary=(
                f"{prompt_funcs} UC function(s) with 'prompt'/'template' in the"
                f" body across {routine_catalogs} catalog(s)"
            ),
            detail=_ROUTINES_SQL,
            rows=[{"prompt_func_count": prompt_funcs, "routine_catalogs": routine_catalogs}],
            ref=_REF,
        )
        audit_evidence = Evidence(
            kind="sql",
            summary=(
                f"{audit_events} serving endpoint config-change event(s) from"
                f" {distinct_users} user(s) in the last 30 days"
            ),
            detail=_AUDIT_SQL,
            rows=[{"prompt_audit_events": audit_events, "distinct_users": distinct_users}],
            ref=_REF,
        )
        limitation = Evidence(
            kind="uc_metadata",
            summary=_PROMPT_LIMITATION,
            detail=(
                "Use UC AI Prompt assets or MLflow prompt logging to version prompts."
                " Store prompt templates as UC functions for lineage and governance."
            ),
            ref=_REF,
        )
        return [routine_evidence, audit_evidence, limitation]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
