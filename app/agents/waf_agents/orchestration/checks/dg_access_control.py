"""Workflow access-control check (LLM-judged).

Answers:
  ORC-DG-03  Control who can create, edit, and run workflows

Two workspace-wide SQL signals are gathered via ctx.sql:
  1. Ratio of jobs that run as a service principal (``run_as`` without '@'),
     from ``system.lakeflow.jobs``.  Broad adoption of service-principal
     identities is a proxy for centralised access control: personal-account
     run_as bypasses RBAC policies and is harder to govern.
  2. Share of jobs that carry at least one tag, also from
     ``system.lakeflow.jobs``.  Tags are used to enforce tag-based access
     policies in Unity Catalog; untagged jobs are harder to scope in policies.

The LLM judge weighs both signals.  Neither fully proves that creation/edit/run
permissions are locked down via ACLs, so LLM confidence is capped at medium.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_SP = (
    "SELECT COUNT(*) AS total_jobs, "
    "SUM(CASE WHEN run_as IS NOT NULL AND run_as <> '' AND run_as NOT LIKE '%@%' "
    "THEN 1 ELSE 0 END) AS sp_jobs "
    "FROM system.lakeflow.jobs "
    "WHERE delete_time IS NULL"
)

_SQL_TAGS = (
    "SELECT COUNT(*) AS total_jobs, "
    "SUM(CASE WHEN size(tags) > 0 THEN 1 ELSE 0 END) AS tagged_jobs "
    "FROM system.lakeflow.jobs "
    "WHERE delete_time IS NULL"
)

_NOTE_SUMMARY = (
    "Workflow ACLs (who may create, edit, and run a job) are enforced at the "
    "Databricks permission layer and are not directly visible in system tables. "
    "Service-principal run_as and tag coverage are indirect proxy signals. "
    "Manual confirmation of ACL configuration needed."
)

_REF = "https://docs.databricks.com/en/workflows/jobs/access-control.html"


@register(layer="orchestration", question_ids=["ORC-DG-03"])
class WorkflowAccessControlCheck(Check):
    """LLM-judged check for ORC-DG-03: access control on workflow creation/editing/running.

    Evidence collected:
      1. Service-principal identity usage as a proxy for centralised RBAC
         (system.lakeflow.jobs, kind ``sql``).
      2. Tag coverage as a proxy for tag-based access policies
         (system.lakeflow.jobs, kind ``sql``).
      3. Caveat noting that ACLs are not directly observable (kind ``note``).
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        # --- evidence 1: service-principal run_as ratio ---
        sp_rows = ctx.sql.query(_SQL_SP)
        sp_row = sp_rows[0] if sp_rows else {}
        total_sp = int(sp_row.get("total_jobs") or 0)
        sp_jobs = int(sp_row.get("sp_jobs") or 0)
        sp_pct = round(100.0 * sp_jobs / total_sp, 1) if total_sp > 0 else 0.0
        ev_sp = Evidence(
            kind="sql",
            summary=(
                f"{sp_jobs} of {total_sp} active jobs run as a service principal "
                f"(run_as without '@') — {sp_pct}%"
            ),
            detail=_SQL_SP,
            rows=[{"total_jobs": total_sp, "sp_jobs": sp_jobs}],
            ref=_REF,
        )

        # --- evidence 2: tag coverage ---
        tag_rows = ctx.sql.query(_SQL_TAGS)
        tag_row = tag_rows[0] if tag_rows else {}
        total_tag = int(tag_row.get("total_jobs") or 0)
        tagged = int(tag_row.get("tagged_jobs") or 0)
        tag_pct = round(100.0 * tagged / total_tag, 1) if total_tag > 0 else 0.0
        ev_tags = Evidence(
            kind="sql",
            summary=(
                f"{tagged} of {total_tag} active jobs carry at least one tag — {tag_pct}%"
            ),
            detail=_SQL_TAGS,
            rows=[{"total_jobs": total_tag, "tagged_jobs": tagged}],
            ref=_REF,
        )

        ev_note = Evidence(
            kind="note",
            summary=_NOTE_SUMMARY,
            rows=[],
            ref=_REF,
        )

        return [ev_sp, ev_tags, ev_note]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
