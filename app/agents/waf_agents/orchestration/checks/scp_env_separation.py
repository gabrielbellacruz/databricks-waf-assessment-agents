"""Environment credential separation check (LLM-judged).

Answers:
  ORC-SCP-05  Separate credentials across environments

There is no system-table column that directly shows whether production and
non-production workflows use different service principals or secret scopes.
The best observable proxy is ``system.lakeflow.jobs``: if the same run_as
identity appears on both jobs whose names suggest a production environment
(e.g. 'prod', 'production') and jobs whose names suggest non-production
(e.g. 'dev', 'test', 'staging', 'qa'), that identity is likely over-privileged
across environments.

This check identifies run_as identities that span both environment groups and
lets the LLM judge weigh the risk. A note records that secret-scope contents
(which would confirm actual credential isolation) are not directly observable.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_MIXED_IDS = """\
SELECT run_as,
       COUNT(*) AS total_jobs,
       SUM(CASE WHEN LOWER(name) LIKE '%prod%'
                  OR LOWER(name) LIKE '%production%'
               THEN 1 ELSE 0 END) AS prod_jobs,
       SUM(CASE WHEN LOWER(name) LIKE '%dev%'
                  OR LOWER(name) LIKE '%test%'
                  OR LOWER(name) LIKE '%staging%'
                  OR LOWER(name) LIKE '%qa%'
               THEN 1 ELSE 0 END) AS non_prod_jobs
FROM system.lakeflow.jobs
WHERE delete_time IS NULL
  AND run_as IS NOT NULL
  AND run_as <> ''
GROUP BY run_as
ORDER BY total_jobs DESC
LIMIT 25\
"""

_SQL_ENV_COUNTS = """\
SELECT
  COUNT(*) AS total_jobs,
  SUM(CASE WHEN LOWER(name) LIKE '%prod%' OR LOWER(name) LIKE '%production%'
      THEN 1 ELSE 0 END) AS prod_named_jobs,
  SUM(CASE WHEN LOWER(name) LIKE '%dev%' OR LOWER(name) LIKE '%test%'
           OR LOWER(name) LIKE '%staging%' OR LOWER(name) LIKE '%qa%'
      THEN 1 ELSE 0 END) AS non_prod_named_jobs
FROM system.lakeflow.jobs
WHERE delete_time IS NULL\
"""

_NOTE = (
    "Environment separation is inferred from job naming conventions only; jobs without "
    "environment indicators in their names are excluded from the analysis. Secret-scope "
    "contents (which would confirm actual credential isolation) are not directly visible "
    "to the agent's service principal. A reviewer should confirm that separate SPs and secret "
    "scopes are used for production vs non-production workflows."
)

_REF = "https://docs.databricks.com/en/security/secrets/secret-scopes.html"


@register(layer="orchestration", question_ids=["ORC-SCP-05"])
class EnvSeparationCheck(Check):
    """Assess credential separation by identifying run_as identities spanning environments.

    Queries system.lakeflow.jobs for run_as identities that appear on both
    prod-named and non-prod-named jobs (a risk signal for shared credentials).
    A companion note records that secret-scope contents are not observable.
    The LLM judge weighs both evidence pieces.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        mixed_rows = ctx.sql.query(_SQL_MIXED_IDS)
        mixed_ids = [
            r for r in mixed_rows
            if int(r.get("prod_jobs") or 0) > 0 and int(r.get("non_prod_jobs") or 0) > 0
        ]

        if mixed_rows:
            mixed_summary = (
                f"{len(mixed_ids)} run_as identities span both prod-named and non-prod-named "
                f"jobs out of {len(mixed_rows)} identities with env-named jobs"
            )
        else:
            mixed_summary = (
                "No jobs with environment-tagged names found; cannot assess credential separation"
            )

        env_rows = ctx.sql.query(_SQL_ENV_COUNTS)
        _empty = {"total_jobs": 0, "prod_named_jobs": 0, "non_prod_named_jobs": 0}
        env_row = env_rows[0] if env_rows else _empty
        total = int(env_row.get("total_jobs") or 0)
        prod_named = int(env_row.get("prod_named_jobs") or 0)
        non_prod_named = int(env_row.get("non_prod_named_jobs") or 0)

        mixed_evidence = Evidence(
            kind="sql",
            summary=mixed_summary,
            detail=_SQL_MIXED_IDS,
            rows=mixed_ids[:15],
            ref=_REF,
        )

        env_coverage_evidence = Evidence(
            kind="sql",
            summary=(
                f"{prod_named} prod-named and {non_prod_named} non-prod-named jobs "
                f"out of {total} total current jobs (by name heuristic)"
            ),
            detail=_SQL_ENV_COUNTS,
            rows=[{
                "total_jobs": total,
                "prod_named_jobs": prod_named,
                "non_prod_named_jobs": non_prod_named,
            }],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [mixed_evidence, env_coverage_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
