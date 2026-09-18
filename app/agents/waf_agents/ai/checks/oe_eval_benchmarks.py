"""AI evaluation benchmarking check (LLM-judged).

Answers:
  AI-OE-01  Compare LLM outputs on a fixed prompt set

Signals are thin: no system table records whether teams maintain fixed-prompt
evaluation sets or run offline comparisons.  Proxies collected:
1. ``system.serving.endpoint_usage``: count of distinct model-serving endpoints
   queried (multiple endpoints suggest exploratory comparison, a weak proxy).
2. ``system.ai_gateway.usage``: distinct gateway endpoints and total call volume
   (high volume may indicate mature AI usage that warrants evaluation practice).

A limitation note records that evaluation datasets, harnesses, and comparison
workflows (e.g. MLflow LLM Evaluate) are NOT observable from system tables, so
the LLM judge should return ``unknown`` / ``low`` confidence when thin.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_ENDPOINT_COUNT_SQL = """\
SELECT COUNT(DISTINCT se.endpoint_name) AS distinct_endpoints,
       COUNT(*) AS total_requests
FROM system.serving.endpoint_usage eu
JOIN system.serving.served_entities se
  ON eu.served_entity_id = se.served_entity_id
WHERE eu.request_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_GATEWAY_MODELS_SQL = """\
SELECT COUNT(DISTINCT endpoint_name) AS gateway_endpoints,
       COUNT(*) AS total_gateway_calls
FROM system.ai_gateway.usage
WHERE event_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_NOTE = (
    "Fixed-prompt evaluation datasets, offline benchmarking runs, and side-by-side model "
    "comparisons are NOT observable from Databricks system tables. The distinct endpoint count "
    "is a weak proxy only: teams evaluating models may query several endpoints, but so do teams "
    "running multiple production apps. Manual confirmation is required to determine whether a "
    "systematic evaluation practice (e.g. MLflow LLM Evaluate, Mosaic Eval Gauntlet) exists."
)

_REF = "https://docs.databricks.com/en/mlflow/llm-evaluate.html"


@register(layer="ai", question_ids=["AI-OE-01"])
class EvalBenchmarksCheck(Check):
    """Assess whether teams compare LLM outputs on a fixed prompt set.

    Evidence is gathered from system.serving.endpoint_usage (distinct endpoints,
    request volumes) and system.ai_gateway.usage (gateway call counts).  A
    limitation note records that evaluation datasets and comparison workflows are
    not visible in system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        endpoint_rows = ctx.sql.query(_ENDPOINT_COUNT_SQL)
        gateway_rows = ctx.sql.query(_GATEWAY_MODELS_SQL)

        if endpoint_rows:
            r = endpoint_rows[0]
            distinct_endpoints = int(r.get("distinct_endpoints") or 0)
            total_requests = int(r.get("total_requests") or 0)
            endpoint_summary = (
                f"{distinct_endpoints} distinct model-serving endpoint(s) queried, "
                f"{total_requests} total requests in the last 30 days "
                "(system.serving.endpoint_usage)"
            )
        else:
            distinct_endpoints = 0
            total_requests = 0
            endpoint_summary = (
                "No rows in system.serving.endpoint_usage for the last 30 days"
            )

        endpoint_evidence = Evidence(
            kind="sql",
            summary=endpoint_summary,
            detail=_ENDPOINT_COUNT_SQL,
            rows=[{"distinct_endpoints": distinct_endpoints, "total_requests": total_requests}],
            ref="https://docs.databricks.com/en/admin/system-tables/serving.html",
        )

        if gateway_rows:
            g = gateway_rows[0]
            gateway_endpoints = int(g.get("gateway_endpoints") or 0)
            total_gateway_calls = int(g.get("total_gateway_calls") or 0)
            gateway_summary = (
                f"{gateway_endpoints} distinct AI Gateway endpoint(s), "
                f"{total_gateway_calls} total calls in the last 30 days "
                "(system.ai_gateway.usage)"
            )
        else:
            gateway_endpoints = 0
            total_gateway_calls = 0
            gateway_summary = "No rows in system.ai_gateway.usage for the last 30 days"

        gateway_evidence = Evidence(
            kind="sql",
            summary=gateway_summary,
            detail=_GATEWAY_MODELS_SQL,
            rows=[{
                "gateway_endpoints": gateway_endpoints,
                "total_gateway_calls": total_gateway_calls,
            }],
            ref="https://docs.databricks.com/en/ai-gateway/index.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [endpoint_evidence, gateway_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
