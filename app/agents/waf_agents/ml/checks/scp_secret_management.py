"""Secret management for ML training and serving code (LLM-judged).

Answers:
  ML-SCP-03  Keep secrets out of training/serving code

Signal: ``system.query.history`` over the last 30 days. Statements that call
``secret()`` or reference ``dbutils.secrets`` are using the Databricks Secret
Manager (good); statements with ``password=``, ``pwd=``, ``token=`` inline are
a risk signal for hard-coded credentials in training or serving notebooks.

This check reuses the same query-history heuristic as the ingestion layer
(ING-SCP-01) and applies it to the ML layer context.

Limitation: secret-scope inventory and job/notebook credential wiring are not
fully observable from query history. Pattern matches on ``password=`` may be
false positives (e.g. SQL DDL comments). A reviewer must verify that training scripts
and model-serving configurations use secret scopes for API keys, database
passwords, and external system credentials.
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
           OR statement_text ILIKE '%token=%'
           OR statement_text ILIKE '%aws_secret%'
      THEN 1 ELSE 0 END) AS possible_hardcoded,
  COUNT(*) AS total_stmts
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Secret-scope inventory and job/notebook credential wiring are not fully observable "
    "to the agent's service principal. This query-history heuristic only surfaces SQL "
    "statement text references; Python SDK calls in notebooks (e.g. "
    "dbutils.secrets.get() without SQL) and model-serving environment variable injection "
    "are not captured in system.query.history. Pattern matches on 'password=' may be false "
    "positives. A reviewer must verify that training scripts and serving configs use secret scopes "
    "for all API keys, database credentials, and external system tokens."
)

_REF = "https://docs.databricks.com/en/security/secrets/index.html"


@register(layer="ml", question_ids=["ML-SCP-03"])
class MlSecretManagementCheck(Check):
    """Count secret-manager references vs possible hard-coded credentials in query history.

    Secret-manager signals: ``secret()`` function or ``dbutils.secrets`` calls (good).
    Hard-coded credential risk: ``password=``, ``pwd=``, ``token=``, ``aws_secret`` patterns.
    A note records that notebook-level Python SDK calls and serving env vars are not
    visible in query history. The LLM judge weighs both pieces.
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

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
