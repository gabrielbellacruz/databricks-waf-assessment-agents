"""Declarative pipeline management check (LLM-judged).

Answers:
  PRO-OE-05  Use declarative management for complex pipelines

Signal: DLT/Lakeflow pipeline count from system.lakeflow.pipelines (baseline)
combined with pipeline configuration details from the artifact API. Declarative
management (DLT, DABs) is evidenced by active pipelines and by pipeline
definitions that show multi-library or continuous configurations.

Mirrors ING-OE-02 (declarative_pipelines) but focuses on whether *complex*
transformation pipelines are managed declaratively rather than ad-hoc, and
requires the LLM to weigh both the ratio and configuration details.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_PIPELINES = "SELECT COUNT(*) AS n FROM system.lakeflow.pipelines"
_SQL_JOBS = "SELECT COUNT(*) AS n FROM system.lakeflow.jobs WHERE delete_time IS NULL"

_NOTE = (
    "Declarative management via Databricks Asset Bundles (DABs) and DLT pipelines is the "
    "recommended approach for complex transformation pipelines. Whether DABs are used for "
    "deployment is not directly observable from system tables; the pipeline count and "
    "configuration details are proxies only. Manual confirmation is needed to verify "
    "bundle-based deployment."
)

_REF = "https://docs.databricks.com/en/dev-tools/bundles/index.html"


@register(layer="processing", question_ids=["PRO-OE-05"])
class DeclarativePipelinesCheck(Check):
    """Assess declarative pipeline management adoption for transformation workloads.

    Gathers DLT/Lakeflow pipeline counts from system tables and, when available,
    pipeline configuration details from the artifact API (library count, continuous
    mode). The LLM judge weighs both the adoption ratio and configuration evidence
    to determine whether complex pipelines are managed declaratively.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        pipeline_rows = ctx.sql.query(_SQL_PIPELINES)
        job_rows = ctx.sql.query(_SQL_JOBS)
        pipelines = int((pipeline_rows[0].get("n") or 0) if pipeline_rows else 0)
        jobs = int((job_rows[0].get("n") or 0) if job_rows else 0)

        count_evidence = Evidence(
            kind="sql",
            summary=(
                f"{pipelines} active DLT/Lakeflow pipeline(s) and {jobs} job(s) "
                "found in system tables"
            ),
            detail=_SQL_PIPELINES + " ; " + _SQL_JOBS,
            rows=[{"pipelines": pipelines, "jobs": jobs}],
            ref=_REF,
        )
        evidence: list[Evidence] = [count_evidence]

        if ctx.artifacts is not None:
            artifact_pipelines = ctx.artifacts.pipelines()
            pipeline_sample = [
                {
                    "name": p.get("spec", p).get("name") or p.get("pipeline_id"),
                    "library_count": len(p.get("spec", p).get("libraries") or []),
                    "continuous": p.get("spec", p).get("continuous", False),
                }
                for p in artifact_pipelines[:15]
            ]
            evidence.append(
                Evidence(
                    kind="pipeline",
                    summary=(
                        f"{len(artifact_pipelines)} pipeline definition(s) available; "
                        "details show library count and continuous/triggered mode"
                    ),
                    rows=pipeline_sample,
                    ref=_REF,
                )
            )

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
