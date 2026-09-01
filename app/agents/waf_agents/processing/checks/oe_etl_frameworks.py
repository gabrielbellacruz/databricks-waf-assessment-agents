"""ETL framework adoption check for transformation pipelines (deterministic).

Answers:
  PRO-OE-01  Use ETL frameworks for transformation pipelines

Signal (MEDIUM confidence — adoption proxy): ratio of active Lakeflow/DLT
pipelines to total transformation workloads (pipelines + jobs) from system tables.
Jobs may include non-transformation workloads; the ratio is an adoption proxy,
not a definitive compliance signal.
Mirrors the ingestion declarative_pipelines pattern re-framed for processing.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.50
_PARTIAL_THRESHOLD = 0.20

# system.lakeflow.pipelines does not expose a delete_time column; no predicate needed.
_SQL_PIPELINES = "SELECT COUNT(*) AS n FROM system.lakeflow.pipelines"
_SQL_JOBS = "SELECT COUNT(*) AS n FROM system.lakeflow.jobs WHERE delete_time IS NULL"

_REF = "https://docs.databricks.com/en/delta-live-tables/index.html"


@register(layer="processing", question_ids=["PRO-OE-01"])
class EtlFrameworksCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        pipeline_rows = ctx.sql.query(_SQL_PIPELINES)
        job_rows = ctx.sql.query(_SQL_JOBS)
        pipelines = int((pipeline_rows[0].get("n") or 0) if pipeline_rows else 0)
        jobs = int((job_rows[0].get("n") or 0) if job_rows else 0)
        return [
            Evidence(
                kind="sql",
                summary=f"{pipelines} active DLT/Lakeflow pipeline(s) found",
                detail=_SQL_PIPELINES,
                rows=[{"n": pipelines}],
                ref=_REF,
            ),
            Evidence(
                kind="sql",
                summary=f"{jobs} active job(s) found (includes non-transformation workloads)",
                detail=_SQL_JOBS,
                rows=[{"n": jobs}],
                ref=_REF,
            ),
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        pipelines = evidence[0].rows[0]["n"]
        jobs = evidence[1].rows[0]["n"]
        total = pipelines + jobs

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No pipelines or jobs found in system tables; "
                    "cannot assess ETL framework adoption."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = pipelines / total
        if ratio >= _MET_THRESHOLD:
            verdict = Verdict.MET
        elif ratio >= _PARTIAL_THRESHOLD:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.NOT_MET

        return Finding(
            question_id=question.id,
            pillar_id=question.pillar_id,
            verdict=verdict,
            confidence=Confidence.MEDIUM,
            score=round(ratio, 4),
            rationale=(
                f"{pipelines} DLT/Lakeflow pipeline(s) and {jobs} job(s) are active "
                f"({ratio:.0%} declarative ETL). Threshold for 'met' is {_MET_THRESHOLD:.0%}. "
                "Note: jobs may include non-transformation workloads; this ratio is an "
                "adoption proxy rather than a precise compliance measure for processing."
            ),
            sources=evidence,
        )
