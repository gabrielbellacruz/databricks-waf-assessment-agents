"""Secret scanning in pipeline code check (LLM-judged).

Answers:
  PRO-SCP-05  Scan pipeline code for hard-coded secrets in CI

Signal: two complementary proxies:
1. Git-backed code coverage — jobs/pipelines sourced from Repos/Git are amenable
   to CI-based secret scanning; those using ad-hoc workspace notebooks are not.
2. Query-history hard-coded credential patterns — statements with 'password=',
   'aws_secret', 'access_key', or 'secret_key' patterns in the last 30 days
   indicate secrets may have leaked into executed code.

The LLM judge combines both signals. A note records that CI secret-scanner
configuration is not observable from system tables and requires manual confirmation.

Combines the source-control signal (ING-OE-03 / PRO-OE-02 pattern) with the
secret-management query-history scan (ING-SCP-01 / PRO-SCP-03 pattern).
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_REPO_HINTS = ("/Repos/", "/Workspace/Repos/")

_SQL = """\
SELECT
  SUM(CASE WHEN statement_text ILIKE '%password=%'
           OR statement_text ILIKE '%aws_secret%'
           OR statement_text ILIKE '%access_key%'
           OR statement_text ILIKE '%secret_key%'
      THEN 1 ELSE 0 END) AS possible_hardcoded,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "CI secret-scanner configuration (GitGuardian, Databricks secrets lint, pre-commit hooks) "
    "is not observable via workspace system tables. Git-backed code coverage is a necessary "
    "but not sufficient condition for CI secret scanning — manual confirmation is needed to verify "
    "that a scanner is actually configured in the CI pipeline."
)

_REF = "https://docs.databricks.com/en/security/secrets/secrets-in-notebooks.html"


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


@register(layer="processing", question_ids=["PRO-SCP-05"])
class SecretScanningCheck(Check):
    """Assess whether pipeline code is structured for CI secret scanning.

    Collects:
    1. Git-backed coverage from artifact API (jobs/pipelines sourced from Git).
    2. Hard-coded credential patterns in query history (last 30 days).
    3. A note on CI scanner observability limits.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        evidence: list[Evidence] = []

        if ctx.artifacts is not None:
            jobs = ctx.artifacts.jobs()
            pipelines = ctx.artifacts.pipelines()
            jobs_git = sum(1 for j in jobs if _job_uses_git(j))
            pipes_git = sum(1 for p in pipelines if _pipeline_uses_git(p))

            evidence.append(
                Evidence(
                    kind="job_config",
                    summary=(
                        f"{jobs_git} of {len(jobs)} jobs and "
                        f"{pipes_git} of {len(pipelines)} pipelines are Git-backed "
                        "(prerequisite for CI secret scanning)"
                    ),
                    rows=[
                        {
                            "jobs_total": len(jobs),
                            "jobs_git_backed": jobs_git,
                            "pipelines_total": len(pipelines),
                            "pipelines_git_backed": pipes_git,
                        }
                    ],
                    ref=_REF,
                )
            )

        qh_rows = ctx.sql.query(_SQL)
        if qh_rows:
            row = qh_rows[0]
            possible_hardcoded = int(row.get("possible_hardcoded") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
            qh_evidence = Evidence(
                kind="sql",
                summary=(
                    f"Possible hard-coded credential patterns in query history: "
                    f"{possible_hardcoded} of {total_stmts} statement(s) (last 30 days)"
                ),
                detail=_SQL,
                rows=[{
                    "possible_hardcoded": possible_hardcoded,
                    "total_stmts": total_stmts,
                }],
                ref=_REF,
            )
        else:
            qh_evidence = Evidence(
                kind="sql",
                summary=(
                    "No query-history rows for the last 30 days"
                    " — cannot scan for hard-coded credential patterns"
                ),
                detail=_SQL,
                rows=[],
                ref=_REF,
            )
        evidence.append(qh_evidence)

        evidence.append(
            Evidence(
                kind="note",
                summary=_NOTE,
                rows=[],
                ref=_REF,
            )
        )
        return evidence

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
