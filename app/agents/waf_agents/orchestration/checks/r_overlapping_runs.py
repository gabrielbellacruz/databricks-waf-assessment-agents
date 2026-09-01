"""Overlapping-runs prevention check for orchestration (deterministic).

Answers:
  ORC-R-04  Prevent overlapping runs of the same workflow

Databricks Workflows defaults to ``max_concurrent_runs = 1``, meaning only one
run of a given job is allowed at a time.  Explicitly setting
``max_concurrent_runs > 1`` allows multiple simultaneous runs and risks
resource contention, duplicate writes, or inconsistent state.

Signal: ratio of non-deleted jobs in ``system.lakeflow.jobs`` where
``max_concurrent_runs`` is NULL (implicit default = 1, protected) or explicitly
<= 1, versus total non-deleted jobs.  A high ratio means the workspace is
protected against accidental concurrency.

Deterministic count ratio → Confidence.HIGH.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.90
_PARTIAL_THRESHOLD = 0.70

_SQL = """\
SELECT COUNT(*) AS total_jobs,
       SUM(CASE WHEN max_concurrent_runs IS NULL OR max_concurrent_runs <= 1
                THEN 1 ELSE 0 END) AS protected_jobs
FROM system.lakeflow.jobs
WHERE delete_time IS NULL\
"""

_REF = "https://docs.databricks.com/en/jobs/settings.html#concurrent-runs"


@register(layer="orchestration", question_ids=["ORC-R-04"])
class OrcOverlappingRunsCheck(Check):
    """Assess concurrent-run protection via max_concurrent_runs in system.lakeflow.jobs.

    Jobs with ``max_concurrent_runs IS NULL`` (default = 1) or explicitly 1 are
    protected against overlapping runs.  The check surfaces the fraction of jobs
    that allow more than one simultaneous run as a compliance ratio.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)
        row = rows[0] if rows else {"total_jobs": 0, "protected_jobs": 0}
        total = int(row.get("total_jobs") or 0)
        protected = int(row.get("protected_jobs") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{protected} of {total} active jobs have max_concurrent_runs "
                    f"= NULL (default 1) or <= 1 — protected from overlapping runs"
                ),
                detail=_SQL,
                rows=[{"total_jobs": total, "protected_jobs": protected}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total_jobs"]
        protected = row["protected_jobs"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No active workflow jobs found in system.lakeflow.jobs; "
                    "cannot evaluate overlapping-run protection."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = protected / total
        if ratio >= _MET_THRESHOLD:
            verdict = Verdict.MET
        elif ratio >= _PARTIAL_THRESHOLD:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.NOT_MET

        unprotected = total - protected
        return Finding(
            question_id=question.id,
            pillar_id=question.pillar_id,
            verdict=verdict,
            confidence=Confidence.HIGH,
            score=round(ratio, 4),
            rationale=(
                f"{protected} of {total} active jobs ({ratio:.0%}) use "
                f"max_concurrent_runs = 1 (or default) and are protected against "
                f"overlapping runs.  {unprotected} job(s) explicitly allow concurrent "
                f"runs (max_concurrent_runs > 1) and should be reviewed.  "
                f"Threshold for 'met' is {_MET_THRESHOLD:.0%}."
            ),
            sources=evidence,
        )
