"""Deploy-code approach for ML check (LLM-judged).

Answers:
  ML-OE-03  Follow the deploy-code approach for ML

Signal: workspace job and pipeline definitions from ``ctx.artifacts`` — whether
ML training and serving jobs source code from a Git repository (via
``git_source`` or a Repos path in the task spec) rather than workspace-local
notebooks. Git-backed code is a prerequisite for the deploy-code pattern:
code that lives in a Repos path or a DABs bundle can be promoted across
environments without notebook export/import.

This check reuses the same artifact inspection logic as the ingestion
source-control check (ING-OE-03) and adapts it to the ML layer. The LLM
judge weighs the ratio of Git-backed jobs / pipelines alongside a note
about the remaining gap (environment promotion, CI/CD) that cannot be
assessed from artifacts alone.

Limitation: the artifact client can only inspect jobs and pipelines; model
training scripts packaged as Python wheels or deployed via DABs bundles may
not appear as ``git_source`` jobs but still follow the deploy-code pattern.
A reviewer must confirm whether a CI/CD promotion workflow exists in addition to
source control.
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


def _pipeline_uses_git(pipeline: dict) -> bool:
    spec = pipeline.get("spec", pipeline)
    for lib in spec.get("libraries", []) or []:
        path = (
            (lib.get("notebook") or {}).get("path")
            or (lib.get("file") or {}).get("path")
            or ""
        )
        if any(h in path for h in _REPO_HINTS):
            return True
    return False


@register(layer="ml", question_ids=["ML-OE-03"])
class MlDeployCodeCheck(Check):
    """Assess deploy-code practice via Git-source inspection of jobs and pipelines.

    Evidence:
    - Artifact jobs: count and sample of jobs sourced from Git / Repos paths.
    - Artifact pipelines: count of pipelines sourced from Repos paths.
    A note records that DABs bundle deployments and Python wheel workflows
    may not appear as git_source jobs but still follow deploy-code practices.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        if ctx.artifacts is None:
            return [
                Evidence(
                    kind="note",
                    summary=(
                        "No artifact client available — job and pipeline "
                        "definitions could not be inspected for Git-source usage."
                    ),
                    rows=[],
                    ref="https://docs.databricks.com/en/repos/index.html",
                )
            ]

        jobs = ctx.artifacts.jobs()
        pipelines = ctx.artifacts.pipelines()

        jobs_git = sum(1 for j in jobs if _job_uses_git(j))
        pipes_git = sum(1 for p in pipelines if _pipeline_uses_git(p))

        job_sample = [
            {
                "name": (j.get("settings", j).get("name") or j.get("job_id")),
                "git_backed": _job_uses_git(j),
            }
            for j in jobs[:15]
        ]

        job_evidence = Evidence(
            kind="job_config",
            summary=(
                f"{jobs_git} of {len(jobs)} jobs run from a Git source or Repos path"
            ),
            rows=job_sample,
            ref="https://docs.databricks.com/en/repos/index.html",
        )

        pipeline_evidence = Evidence(
            kind="pipeline",
            summary=(
                f"{pipes_git} of {len(pipelines)} pipelines source their code from a Repo"
            ),
            rows=[
                {
                    "pipelines_total": len(pipelines),
                    "pipelines_git_backed": pipes_git,
                }
            ],
            ref="https://docs.databricks.com/en/dev-tools/bundles/index.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=(
                "Python wheel deployments, DABs bundle jobs, and Databricks Apps "
                "may implement the deploy-code pattern without a visible git_source field. "
                "The artifact inspection here covers jobs and DLT pipelines only. A reviewer must "
                "confirm whether CI/CD promotion (dev -> staging -> prod) is wired up."
            ),
            rows=[],
            ref="https://docs.databricks.com/en/dev-tools/bundles/index.html",
        )

        return [job_evidence, pipeline_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
