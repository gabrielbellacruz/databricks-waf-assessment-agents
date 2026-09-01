"""Service-principal job identity check for transformation jobs.

Answers:
  PRO-SCP-01  Run transformation jobs as service principals

Signal: share of current jobs whose run_as identity looks like a service principal
(no '@' in the string) vs a human user (contains '@'), from system.lakeflow.jobs.
MEDIUM confidence: identity classification is a heuristic, and all workspace jobs
serve as a proxy for "transformation" jobs specifically.

Mirrors the ingestion service_principal_jobs check exactly, re-framed for
transformation workloads.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.90
_PARTIAL_THRESHOLD = 0.50

_SQL = (
    "SELECT COUNT(*) AS total, "
    "SUM(CASE WHEN run_as IS NOT NULL AND run_as <> '' AND run_as NOT LIKE '%@%' "
    "THEN 1 ELSE 0 END) AS sp_jobs "
    "FROM system.lakeflow.jobs "
    "WHERE delete_time IS NULL"
)


@register(layer="processing", question_ids=["PRO-SCP-01"])
class ServicePrincipalJobsCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total": 0, "sp_jobs": 0}
        total = int(row.get("total") or 0)
        sp_jobs = int(row.get("sp_jobs") or 0)
        return [
            Evidence(
                kind="sql",
                summary=f"{sp_jobs} of {total} current jobs run as a service principal",
                detail=_SQL,
                rows=[{"total": total, "sp_jobs": sp_jobs}],
                ref="https://docs.databricks.com/en/dev-tools/service-principals.html",
            )
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        row = evidence[0].rows[0]
        total, sp_jobs = row["total"], row["sp_jobs"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No jobs found in system.lakeflow.jobs to evaluate "
                    "service-principal usage."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = sp_jobs / total
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
                f"{sp_jobs} of {total} current jobs ({ratio:.0%}) have a run_as identity "
                f"without '@', indicating a service principal rather than a human user; "
                f"threshold for 'met' is {_MET_THRESHOLD:.0%}. "
                "Confidence is MEDIUM: identity classification is a heuristic (run_as "
                "without '@' is treated as a service principal, which may misclassify "
                "unusual username formats), and all workspace jobs are used as a proxy "
                "for transformation jobs specifically."
            ),
            sources=evidence,
        )
