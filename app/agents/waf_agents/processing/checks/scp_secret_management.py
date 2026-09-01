"""Secret management in transformation code check (LLM-judged).

Answers:
  PRO-SCP-03  Keep secrets out of transformation code

Mirrors the ingestion secret_management check re-framed for transformation
pipelines and jobs. Query-history text is scanned for secret() / dbutils.secrets
references (good signal) and for possible hard-coded credential patterns (risk
signal). A note records the observability limits of this heuristic.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_SQL = """\
SELECT
  SUM(CASE WHEN statement_text ILIKE '%secret(%'
           OR statement_text ILIKE '%dbutils.secrets%'
      THEN 1 ELSE 0 END) AS secret_ref_stmts,
  SUM(CASE WHEN statement_text ILIKE '%password=%'
           OR statement_text ILIKE '%pwd=%'
           OR statement_text ILIKE '%aws_secret%'
           OR statement_text ILIKE '%access_key%'
      THEN 1 ELSE 0 END) AS possible_hardcoded,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Secret-scope wiring in transformation jobs and pipelines is not directly observable "
    "to the agent's service principal; this query-history heuristic surfaces references "
    "in SQL statements only. 'possible_hardcoded' matches may be false positives "
    "(e.g., legitimate parameter names). Python or Scala code outside SQL statements "
    "is not scanned. Manual confirmation required."
)

_REF = "https://docs.databricks.com/en/security/secrets/index.html"


@register(layer="processing", question_ids=["PRO-SCP-03"])
class SecretManagementCheck(Check):
    """Scan query history for secret-manager references vs possible hard-coded credentials.

    Secret-manager signals: ``secret()`` function or ``dbutils.secrets`` calls (good).
    Hard-coded credential risk: ``password=``, ``pwd=``, ``aws_secret``, ``access_key``
    patterns. A companion note records the limited observability of this heuristic.
    The LLM judge weighs both signals.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_SQL)

        if rows:
            row = rows[0]
            secret_ref_stmts = int(row.get("secret_ref_stmts") or 0)
            possible_hardcoded = int(row.get("possible_hardcoded") or 0)
            total_stmts = int(row.get("total_stmts") or 0)
            summary = (
                f"Secret-manager references (secret()/dbutils.secrets)={secret_ref_stmts}"
                f" (good); possible hard-coded credential patterns={possible_hardcoded}"
                f" (risk); total statements={total_stmts} (last 30 days)"
            )
            sql_evidence = Evidence(
                kind="sql",
                summary=summary,
                detail=_SQL,
                rows=[
                    {
                        "secret_ref_stmts": secret_ref_stmts,
                        "possible_hardcoded": possible_hardcoded,
                        "total_stmts": total_stmts,
                    }
                ],
                ref=_REF,
            )
        else:
            sql_evidence = Evidence(
                kind="sql",
                summary=(
                    "No query-history rows returned for the last 30 days"
                    " — cannot assess secret-management usage"
                ),
                detail=_SQL,
                rows=[],
                ref=_REF,
            )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )
        return [sql_evidence, note_evidence]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
