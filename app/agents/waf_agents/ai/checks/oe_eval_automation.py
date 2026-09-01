"""Automated LLM evaluation in pipeline check (LLM-judged).

Answers:
  AI-OE-02  Automate LLM evaluation in the pipeline

Signals:
1. ``system.access.audit``: service-name ``mlflowAcledArtifact`` or ``serving``
   events from service-principal identities suggest automated (pipeline-driven)
   use of model endpoints — a proxy for automated evaluation runs.
2. ``system.lakeflow.job_run_timeline``: recent scheduled-job volume as a proxy
   for pipeline automation (no column distinguishes eval jobs from production).

A limitation note records that job purpose and LLM evaluation tooling (MLflow
LLM Evaluate, etc.) are NOT observable from system tables.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SP_SERVING_SQL = """\
SELECT COUNT(*) AS sp_serving_calls,
       COUNT(DISTINCT user_identity.email) AS distinct_principals
FROM system.access.audit
WHERE service_name IN ('serving', 'mlflowAcledArtifact', 'mlflowEndpoints')
  AND event_date >= current_date() - INTERVAL 30 DAYS
  AND user_identity.user_type = 'servicePrincipal'\
"""

_JOB_RUNS_SQL = """\
SELECT COUNT(*) AS total_runs,
       COUNT(DISTINCT job_id) AS distinct_jobs
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Automated LLM evaluation pipelines (e.g. scheduled MLflow Evaluate jobs, "
    "CI/CD hooks that score models before promotion) are not distinguishable from "
    "production workloads in system tables. Service-principal access to serving endpoints "
    "is a weak proxy for automation but does not confirm an evaluation workflow. "
    "Job run counts confirm pipeline activity but not evaluation purpose. "
    "A reviewer must verify whether a dedicated eval pipeline exists."
)

_REF = "https://docs.databricks.com/en/mlflow/llm-evaluate.html"


@register(layer="ai", question_ids=["AI-OE-02"])
class EvalAutomationCheck(Check):
    """Assess whether LLM evaluation is automated in the delivery pipeline.

    Evidence:
    - system.access.audit: service-principal calls to serving/MLflow endpoints
      (proxy for automated eval invocations).
    - system.lakeflow.job_run_timeline: pipeline job activity (proxy for
      automation in general).
    A note records that eval-specific jobs cannot be identified from system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        sp_rows = ctx.sql.query(_SP_SERVING_SQL)
        job_rows = ctx.sql.query(_JOB_RUNS_SQL)

        if sp_rows:
            r = sp_rows[0]
            sp_calls = int(r.get("sp_serving_calls") or 0)
            distinct_principals = int(r.get("distinct_principals") or 0)
            sp_summary = (
                f"{sp_calls} serving/MLflow audit events from service principals "
                f"({distinct_principals} distinct SP(s)) in the last 30 days — "
                "proxy for automated model access"
            )
        else:
            sp_calls = 0
            distinct_principals = 0
            sp_summary = (
                "No service-principal serving/MLflow audit events found "
                "in system.access.audit for the last 30 days"
            )

        sp_evidence = Evidence(
            kind="sql",
            summary=sp_summary,
            detail=_SP_SERVING_SQL,
            rows=[{"sp_serving_calls": sp_calls, "distinct_principals": distinct_principals}],
            ref="https://docs.databricks.com/en/admin/system-tables/audit.html",
        )

        if job_rows:
            j = job_rows[0]
            total_runs = int(j.get("total_runs") or 0)
            distinct_jobs = int(j.get("distinct_jobs") or 0)
            job_summary = (
                f"{total_runs} job run(s) across {distinct_jobs} distinct job(s) "
                "in the last 30 days (system.lakeflow.job_run_timeline)"
            )
        else:
            total_runs = 0
            distinct_jobs = 0
            job_summary = (
                "No job runs found in system.lakeflow.job_run_timeline "
                "for the last 30 days"
            )

        job_evidence = Evidence(
            kind="sql",
            summary=job_summary,
            detail=_JOB_RUNS_SQL,
            rows=[{"total_runs": total_runs, "distinct_jobs": distinct_jobs}],
            ref="https://docs.databricks.com/en/admin/system-tables/lakeflow.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [sp_evidence, job_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
