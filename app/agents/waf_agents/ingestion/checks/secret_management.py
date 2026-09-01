"""Secret-management credential check (LLM-judged).

Answers:
  ING-SCP-01  Store source-system credentials with secret management

There is no system-table column that directly shows whether individual jobs or
pipelines use a secret scope rather than a hard-coded password. The best
observable proxy is query-history text: statements that call ``secret()`` or
``dbutils.secrets`` reference the secret manager (good signal); statements
containing ``password=``, ``pwd=``, or ``aws_secret`` inline are a risk signal.
This check counts both patterns over the last 90 days and lets the LLM judge
weigh them, paired with a note that records the limits of this heuristic.
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
      THEN 1 ELSE 0 END) AS possible_hardcoded,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 90 DAYS\
"""

_NOTE = (
    "Secret-scope inventory and job credential wiring are not fully observable to the"
    " agent's service principal; this query-history heuristic only surfaces references,"
    " and 'possible_hardcoded' matches may be false positives. Manual confirmation needed."
)

_REF = "https://docs.databricks.com/en/security/secrets/index.html"


@register(layer="ingestion", question_ids=["ING-SCP-01"])
class SecretManagementCheck(Check):
    """Count secret-manager references vs possible hard-coded credentials in query history.

    Secret-manager signals: ``secret()`` function or ``dbutils.secrets`` calls (good).
    Hard-coded credential risk: ``password=``, ``pwd=``, ``aws_secret`` patterns.
    A companion note records that job-level credential wiring is not directly observable
    and that pattern matches may be false positives. The LLM judge weighs both pieces.
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
                f" (risk); total statements={total_stmts} (last 90 days)"
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
                    "No query-history rows returned for the last 90 days"
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

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
