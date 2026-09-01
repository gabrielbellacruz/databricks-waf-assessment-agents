"""Service-principal identity check for ML training jobs (deterministic).

Answers:
  ML-SCP-01  Run training and serving as service principals

Signal: share of current jobs whose ``run_as`` identity looks like a service
principal (no ``@`` in the string) vs a human user (contains ``@``), from
``system.lakeflow.jobs``. All workspace jobs are used as a proxy for ML
training jobs because the system table does not label jobs by purpose.

This follows the same heuristic as the ingestion layer (ING-SCP-04) but
applies to the ML layer.

Confidence is MEDIUM: the ``@``-heuristic may misclassify unusual usernames,
and all jobs (not just ML training jobs) serve as the denominator.

Serving endpoint ``run_as`` identity is NOT observable from system tables;
the agent's service principal cannot enumerate serving endpoint configurations.
A limitation note is attached to prompt manual review of serving endpoint identities.
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

_SERVING_NOTE = (
    "Serving endpoint 'run_as' identity is set in the endpoint configuration and is "
    "NOT exposed in system.lakeflow.jobs or system.serving.endpoint_usage. The agent's "
    "service principal cannot enumerate serving endpoint run_as settings. A reviewer must verify "
    "that model-serving endpoints are configured to run as service principals via "
    "GET /api/2.0/serving-endpoints/{name}."
)

_REF = "https://docs.databricks.com/en/dev-tools/service-principals.html"


@register(layer="ml", question_ids=["ML-SCP-01"])
class MlServicePrincipalCheck(Check):
    """Assess whether ML jobs run as service principals via system.lakeflow.jobs.

    Deterministic: ratio of SP jobs to total is thresholded at MET (>=90%),
    PARTIAL (50-89%), NOT_MET (<50%). Empty denominator yields UNKNOWN/LOW.
    A second evidence note records that serving endpoint run_as is not
    observable and requires manual inspection.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total": 0, "sp_jobs": 0}
        total = int(row.get("total") or 0)
        sp_jobs = int(row.get("sp_jobs") or 0)

        job_evidence = Evidence(
            kind="sql",
            summary=(
                f"{sp_jobs} of {total} current jobs run as a service principal "
                "(run_as without '@')"
            ),
            detail=_SQL,
            rows=[{"total": total, "sp_jobs": sp_jobs}],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_SERVING_NOTE,
            rows=[],
            ref=_REF,
        )

        return [job_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
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
                    "service-principal usage for ML training."
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
                "Confidence is MEDIUM: identity classification is a heuristic "
                "(run_as without '@' treated as SP), and all workspace jobs serve as a proxy "
                "for ML training jobs. Serving endpoint run_as requires separate manual review."
            ),
            sources=evidence,
        )
