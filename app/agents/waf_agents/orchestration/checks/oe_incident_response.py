"""Workflow incident-response process check (LLM-judged).

Answers:
  ORC-OE-05  Define an incident response process for workflow failures

No single system-table value captures whether a team has a documented
incident-response playbook for workflow failures. The closest observable
proxies are:

  1. Volume and pattern of manual re-runs (``runNow`` events in
     ``system.access.audit``) - a team that remediates quickly will trigger
     manual re-runs after failures.
  2. High recent failure counts with no sign of manual intervention suggest
     failures are going unnoticed (weak counter-signal).

Both are weak signals; the LLM judge is expected to lean toward ``unknown``
and note that a reviewer must confirm whether a documented incident-response
process exists.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL_FAILURES = """\
SELECT COUNT(*) AS total_runs,
       SUM(CASE WHEN result_state IN ('FAILED','ERROR','TIMED_OUT') THEN 1 ELSE 0 END)
           AS failed_runs
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_SQL_MANUAL_RERUNS = """\
SELECT COUNT(*) AS manual_run_events
FROM system.access.audit
WHERE service_name = 'jobs'
  AND action_name = 'runNow'
  AND event_date >= current_date() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "A documented incident-response process (runbooks, on-call rotations, escalation "
    "paths) is not observable from system tables. Manual re-run events are a weak proxy "
    "for active remediation; they could also be routine ad-hoc runs. A reviewer must confirm "
    "whether a formal incident-response process exists for workflow failures."
)

_REF = "https://docs.databricks.com/en/workflows/jobs/monitor-job.html"


@register(layer="orchestration", question_ids=["ORC-OE-05"])
class IncidentResponseCheck(Check):
    """Assess incident-response maturity via manual re-run activity and failure rate.

    Gathers recent failure counts from job_run_timeline and manual runNow events
    from system.access.audit as weak proxies for active incident response.
    A note evidence records the hard limitation. The LLM judge weighs both.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        failure_rows = ctx.sql.query(_SQL_FAILURES)
        if failure_rows:
            total = int(failure_rows[0].get("total_runs") or 0)
            failed = int(failure_rows[0].get("failed_runs") or 0)
        else:
            total = 0
            failed = 0

        failure_pct = round(100.0 * failed / total, 1) if total > 0 else 0.0
        failure_summary = (
            f"{failed} of {total} job runs failed/errored/timed-out in the last 30 days "
            f"({failure_pct}%)"
            if total > 0
            else "No job runs found in system.lakeflow.job_run_timeline for the last 30 days"
        )

        rerun_rows = ctx.sql.query(_SQL_MANUAL_RERUNS)
        manual_runs = int(rerun_rows[0].get("manual_run_events") or 0) if rerun_rows else 0

        failure_evidence = Evidence(
            kind="sql",
            summary=failure_summary,
            detail=_SQL_FAILURES,
            rows=[{"total_runs": total, "failed_runs": failed, "failure_pct": failure_pct}],
            ref=_REF,
        )

        rerun_evidence = Evidence(
            kind="sql",
            summary=(
                f"{manual_runs} manual runNow events in system.access.audit in the last 30 days "
                "(proxy for active re-run/remediation activity)"
            ),
            detail=_SQL_MANUAL_RERUNS,
            rows=[{"manual_run_events": manual_runs}],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [failure_evidence, rerun_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
