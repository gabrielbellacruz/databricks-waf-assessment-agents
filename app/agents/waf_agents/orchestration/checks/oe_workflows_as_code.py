"""Workflows-as-code / CI-CD check (LLM-judged).

Answers:
  ORC-OE-02  Define workflows as code with CI/CD

There is no single system-table number for "job definitions live in source
control with a CI/CD pipeline." The signal is spread across job and pipeline
definitions: whether tasks run from a git_source (an explicit Git provider
reference) or from a Repos-backed path, versus ad-hoc workspace notebooks.
This check gathers those configuration artifacts and lets the LLM judge weigh
them.

Pattern: direct reuse of the ingestion source-control check, re-framed for
orchestration workflows.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_REPO_HINTS = ("/Repos/", "/Workspace/Repos/")


def _job_uses_git(job: dict) -> bool:
    settings = job.get("settings", job)
    if settings.get("git_source"):
        return True
    for task in settings.get("tasks", []) or []:
        if task.get("git_source"):
            return True
        for key in ("notebook_task", "spark_python_task", "python_wheel_task", "sql_task"):
            spec = task.get(key) or {}
            path = spec.get("notebook_path") or spec.get("python_file") or ""
            if any(h in path for h in _REPO_HINTS):
                return True
    return False


@register(layer="orchestration", question_ids=["ORC-OE-02"])
class OrcWorkflowsAsCodeCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        if ctx.artifacts is None:
            return [
                Evidence(
                    kind="note",
                    summary=(
                        "Artifact client not available; git_source configuration cannot be "
                        "checked. A reviewer should confirm whether job definitions are managed in "
                        "source control with CI/CD."
                    ),
                )
            ]

        jobs = ctx.artifacts.jobs()
        jobs_git = sum(1 for j in jobs if _job_uses_git(j))

        job_sample = [
            {
                "name": (j.get("settings", j).get("name") or j.get("job_id")),
                "git_backed": _job_uses_git(j),
            }
            for j in jobs[:15]
        ]

        return [
            Evidence(
                kind="job_config",
                summary=(
                    f"{jobs_git} of {len(jobs)} jobs run from a Git source or Repos path; "
                    f"{len(jobs) - jobs_git} run from ad-hoc workspace notebooks"
                ),
                rows=job_sample,
                ref="https://docs.databricks.com/en/repos/index.html",
            ),
            Evidence(
                kind="note",
                summary=(
                    "Git source coverage only captures jobs with an explicit git_source block "
                    "or a /Repos/ notebook path. Jobs managed via Databricks Asset Bundles "
                    "deployed from CI/CD pipelines may appear without a git_source in the "
                    "API response; manual confirmation is needed for full CI/CD coverage."
                ),
                ref="https://docs.databricks.com/en/dev-tools/bundles/index.html",
            ),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
