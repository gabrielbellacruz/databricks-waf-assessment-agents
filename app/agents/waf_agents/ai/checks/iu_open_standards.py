"""Open standards adoption in AI workflows check (LLM-judged).

Answers:
  AI-IU-01  Use open standards for AI workflows

Signal:
  1. system.access.audit — MLflow API calls (logModel, logMetrics, createRun,
     etc.) indicate use of the open MLflow standard for experiment tracking.
  2. system.billing.usage — Foundation Model API SKUs are proxies for open-API
     (OpenAI-compatible REST) endpoint usage, which is Databricks' open-standard
     serving interface.

Limitation note: Whether actual framework code uses open standards (LangChain,
LlamaIndex, OpenAI SDK, MLflow AI Gateway) is not visible from system tables
alone. The presence of MLflow audit events and FMAPI billing is a positive but
indirect signal.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_AUDIT_SQL = (
    "SELECT COUNT(*) AS mlflow_audit_count,"
    " COUNT(DISTINCT user_identity.email) AS mlflow_users"
    " FROM system.access.audit"
    " WHERE action_name IN ("
    "  'logModel','logMetrics','logParams','createRun','updateRun',"
    "  'createExperiment','setExperimentTag'"
    " )"
    " AND CAST(event_time AS DATE) >= CURRENT_DATE - INTERVAL 30 DAYS"
)

_BILLING_SQL = (
    "SELECT COUNT(*) AS fmapi_dbus,"
    " SUM(usage_quantity) AS total_dbus"
    " FROM system.billing.usage"
    " WHERE LOWER(sku_name) LIKE '%foundation_model%'"
    "    OR LOWER(sku_name) LIKE '%fmapi%'"
    "    OR LOWER(sku_name) LIKE '%external_model%'"
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/index.html"

_STANDARDS_LIMITATION = (
    "Whether AI application code uses open frameworks (MLflow, LangChain,"
    " LlamaIndex, OpenAI SDK, Hugging Face Transformers) is not visible from system"
    " tables. MLflow audit events and Foundation Model API billing rows are proxies"
    " but do not guarantee fully open-standard workflows."
)


@register(layer="ai", question_ids=["AI-IU-01"])
class AiOpenStandardsCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        audit_rows = ctx.sql.query(_AUDIT_SQL)
        billing_rows = ctx.sql.query(_BILLING_SQL)

        a = audit_rows[0] if audit_rows else {}
        mlflow_events = int(a.get("mlflow_audit_count") or 0)
        mlflow_users = int(a.get("mlflow_users") or 0)

        b = billing_rows[0] if billing_rows else {}
        fmapi_rows = int(b.get("fmapi_dbus") or 0)
        total_dbus = float(b.get("total_dbus") or 0.0)

        audit_evidence = Evidence(
            kind="sql",
            summary=(
                f"{mlflow_events} MLflow API event(s) from {mlflow_users} user(s)"
                " in the last 30 days (open-standard experiment tracking)"
            ),
            detail=_AUDIT_SQL,
            rows=[{"mlflow_audit_count": mlflow_events, "mlflow_users": mlflow_users}],
            ref=_REF,
        )
        billing_evidence = Evidence(
            kind="sql",
            summary=(
                f"{fmapi_rows} Foundation Model API billing row(s) totalling"
                f" {total_dbus:.2f} DBUs (open-API endpoint usage)"
            ),
            detail=_BILLING_SQL,
            rows=[{"fmapi_dbus": fmapi_rows, "total_dbus": total_dbus}],
            ref=_REF,
        )
        limitation = Evidence(
            kind="uc_metadata",
            summary=_STANDARDS_LIMITATION,
            detail=(
                "Review notebooks, Repos, and job libraries for LangChain / LlamaIndex"
                " / MLflow imports to confirm open-standards adoption."
            ),
            ref=_REF,
        )
        return [audit_evidence, billing_evidence, limitation]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
