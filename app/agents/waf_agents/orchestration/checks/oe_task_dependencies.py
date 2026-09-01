"""Task-dependency modelling check (LLM-judged).

Answers:
  ORC-OE-03  Model task dependencies explicitly

There is no system-table column that records whether a multi-task job has
explicit ``depends_on`` relationships configured between its tasks. The signal
comes from job definitions via the artifact API: multi-task jobs that configure
``depends_on`` have a declared dependency graph; those where every task runs
independently (no ``depends_on``) may be hiding implicit ordering assumptions
or missing error-propagation semantics.

The LLM judge weighs the fraction of multi-task jobs with explicit dependencies,
together with a note about single-task jobs which cannot be assessed.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register


def _task_count(job: dict) -> int:
    settings = job.get("settings", job)
    return len(settings.get("tasks", []) or [])


def _has_explicit_deps(job: dict) -> bool:
    """True when any task in the job declares a depends_on block."""
    settings = job.get("settings", job)
    tasks = settings.get("tasks", []) or []
    return any(bool(t.get("depends_on")) for t in tasks)


@register(layer="orchestration", question_ids=["ORC-OE-03"])
class TaskDependenciesCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        if ctx.artifacts is None:
            return [
                Evidence(
                    kind="note",
                    summary=(
                        "Artifact client not available; task dependency configuration cannot "
                        "be checked. A reviewer should confirm whether multi-task jobs declare "
                        "explicit depends_on relationships."
                    ),
                )
            ]

        jobs = ctx.artifacts.jobs()
        multi_task = [j for j in jobs if _task_count(j) > 1]
        with_deps = sum(1 for j in multi_task if _has_explicit_deps(j))
        single_task = len(jobs) - len(multi_task)

        sample = [
            {
                "name": (j.get("settings", j).get("name") or j.get("job_id")),
                "task_count": _task_count(j),
                "explicit_deps": _has_explicit_deps(j),
            }
            for j in multi_task[:15]
        ]

        dep_evidence = Evidence(
            kind="job_config",
            summary=(
                f"{with_deps} of {len(multi_task)} multi-task jobs declare explicit "
                f"task dependencies (depends_on); {single_task} single-task jobs are "
                "not applicable"
            ),
            rows=sample,
            ref="https://docs.databricks.com/en/workflows/jobs/tasks.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=(
                "depends_on configuration is only visible via the Jobs REST API; "
                "single-task jobs are excluded from this assessment. "
                "Implicit ordering (e.g. sequential notebooks without declared deps) "
                "is not detectable from the API response."
            ),
            ref="https://docs.databricks.com/en/workflows/jobs/tasks.html",
        )

        return [dep_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
