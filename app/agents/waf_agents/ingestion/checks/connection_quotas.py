"""Connection-quota check (LLM-judged).

Answers:
  ING-OE-05  Manage source connection limits and API quotas

There is no system-table column that records connector concurrency settings
or per-source rate-limit configuration. The closest observable proxy is the
*presence of throttle/rate-limit keywords* in recent query-history statements:
statements whose text mentions "rate limit", "throttl", "429", or "quota" are
indirect evidence that connection limits are being hit. The LLM judge weighs
this weak signal together with a note explaining the fundamental observability
gap, and returns a verdict a reviewer can confirm or override.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  SUM(CASE WHEN statement_text ILIKE '%rate limit%'
        OR statement_text ILIKE '%throttl%'
        OR statement_text ILIKE '%429%'
        OR statement_text ILIKE '%quota%' THEN 1 ELSE 0 END) AS throttle_mentions,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 90 DAYS"""

_REF = "https://docs.databricks.com/en/ingestion/index.html"

_CONFIG_NOTE = (
    "Source-system connection limits and API-quota handling (e.g. maxFilesPerTrigger,"
    " connector concurrency, job max_concurrent_runs) are set in job/pipeline/connector"
    " configuration that is not exposed in system tables and not enumerable by this"
    " agent's service principal. The query-history throttle heuristic is only weak,"
    " indirect evidence — manual confirmation needed."
)


@register(layer="ingestion", question_ids=["ING-OE-05"])
class ConnectionQuotasCheck(Check):
    """Assess API-quota and rate-limit handling via query-history keyword heuristic.

    Evidence is gathered from ``system.query.history`` over the last 90 days:
    statements whose text mentions rate-limit or throttling signals are counted.
    A second note evidence records that connection-limit *configuration* is not
    visible to the agent and must be confirmed manually. The LLM judge weighs
    both pieces and produces a verdict a reviewer can confirm or override.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            throttle_mentions = int(rows[0].get("throttle_mentions") or 0)
            total_stmts = int(rows[0].get("total_stmts") or 0)
        else:
            throttle_mentions = 0
            total_stmts = 0

        summary = (
            f"throttle/rate-limit keyword mentions={throttle_mentions}"
            f" in statement_text; total statements={total_stmts} (last 90 days)"
        )

        sql_evidence = Evidence(
            kind="sql",
            summary=summary,
            detail=_SQL,
            rows=[{"throttle_mentions": throttle_mentions, "total_stmts": total_stmts}],
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_CONFIG_NOTE,
            rows=[],
            ref=_REF,
        )

        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
