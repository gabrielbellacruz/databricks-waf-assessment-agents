"""Source-control / CI-CD check (LLM-judged exemplar).

Answers:
  ING-OE-03  Manage ingestion pipeline code in source control with CI/CD

There's no single system-table number for "code is in Git with CI/CD". The
signal is spread across job and pipeline definitions: whether tasks run from a
Git source (``git_source`` / a Repos path) versus ad-hoc workspace notebooks.
This check gathers those config artifacts and lets the LLM judge weigh them.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

# Workspace-source paths that indicate Git-backed code (a Databricks Repo).
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


def _pipeline_uses_git(pipeline: dict) -> bool:
    spec = pipeline.get("spec", pipeline)
    for lib in spec.get("libraries", []) or []:
        path = (lib.get("notebook") or {}).get("path") or (lib.get("file") or {}).get("path") or ""
        if any(h in path for h in _REPO_HINTS):
            return True
    return False


@register(layer="ingestion", question_ids=["ING-OE-03"])
class SourceControlCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        if ctx.artifacts is None:
            return []

        jobs = ctx.artifacts.jobs()
        pipelines = ctx.artifacts.pipelines()

        jobs_git = sum(1 for j in jobs if _job_uses_git(j))
        pipes_git = sum(1 for p in pipelines if _pipeline_uses_git(p))

        # A small, non-sensitive sample so the judge sees concrete names.
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
                summary=f"{jobs_git} of {len(jobs)} jobs run from a Git source or Repos path",
                rows=job_sample,
                ref="https://docs.databricks.com/en/repos/index.html",
            ),
            Evidence(
                kind="pipeline",
                summary=f"{pipes_git} of {len(pipelines)} pipelines source their code from a Repo",
                rows=[{"pipelines_total": len(pipelines), "pipelines_git_backed": pipes_git}],
                ref="https://docs.databricks.com/en/dev-tools/bundles/index.html",
            ),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
