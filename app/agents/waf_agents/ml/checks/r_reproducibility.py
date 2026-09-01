"""Reproducible training runs check (LLM-judged).

Answers:
  ML-R-03  Ensure reproducible training runs

Reproducibility requires fixed random seeds, pinned library versions, a
versioned training dataset, and a consistent environment (e.g. MLflow
autologging with an environment snapshot). None of these are directly
observable from system tables: MLflow experiment parameters and dataset
hashes are stored in MLflow tracking, not in system.lakeflow or
system.billing. The observable proxy is whether jobs show consistent
run-count patterns (re-runs suggest a lack of idempotence; a very high
retry rate can indicate non-deterministic failures). A strong limitation
note accompanies all evidence so the LLM judge and a reviewer understand what
cannot be automated.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

# Distinct needle: "period_end_time" is unique to this query among all ML checks.
_SQL = """\
SELECT
  COUNT(*) AS total_runs,
  COUNT(DISTINCT job_id) AS distinct_jobs,
  SUM(CASE WHEN result_state = 'FAILED' THEN 1 ELSE 0 END) AS failed_runs,
  ROUND(
    AVG(
      TIMESTAMPDIFF(SECOND, period_start_time, period_end_time)
    ), 1
  ) AS avg_duration_s
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS
  AND period_end_time IS NOT NULL\
"""

_NOTE = (
    "Reproducibility (fixed random seeds, pinned library/dataset versions, environment "
    "snapshots) is stored in MLflow experiment tracking and job configuration — neither "
    "is accessible via system tables or this agent's service principal. Run consistency "
    "statistics are only a very weak proxy; manual review of MLflow experiment setup and "
    "cluster/library configuration is required to assess reproducibility."
)

_REF = "https://docs.databricks.com/en/machine-learning/track-model-development/index.html"


@register(layer="ml", question_ids=["ML-R-03"])
class MlReproducibilityCheck(Check):
    """Assess training reproducibility via job-run consistency statistics.

    Evidence is gathered from system.lakeflow.job_run_timeline (last 30
    days): total runs, distinct jobs, failure count, and average duration.
    A limitation note makes explicit that fixed seeds, pinned versions, and
    MLflow autologging configuration are not observable from system tables.
    The LLM judge weighs the weak proxy evidence and is expected to return
    'unknown' unless there are strong negative signals.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            total = int(row.get("total_runs") or 0)
            distinct_jobs = int(row.get("distinct_jobs") or 0)
            failed = int(row.get("failed_runs") or 0)
            avg_dur = row.get("avg_duration_s")
        else:
            total = distinct_jobs = failed = 0
            avg_dur = None

        if total > 0:
            fail_pct = round(100.0 * failed / total, 1)
            dur_str = f"; avg run duration {avg_dur}s" if avg_dur is not None else ""
            sql_summary = (
                f"{total} completed job runs across {distinct_jobs} distinct jobs "
                f"in the last 30 days; {failed} failures ({fail_pct}%){dur_str}"
            )
        else:
            sql_summary = (
                "No completed job runs found in system.lakeflow.job_run_timeline "
                "for the last 30 days"
            )

        sql_evidence = Evidence(
            kind="sql",
            summary=sql_summary,
            detail=_SQL,
            rows=[
                {
                    "total_runs": total,
                    "distinct_jobs": distinct_jobs,
                    "failed_runs": failed,
                    "avg_duration_s": avg_dur,
                }
            ],
            ref="https://docs.databricks.com/en/monitoring/system-tables/lakeflow.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
