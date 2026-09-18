"""Model-choice cost-optimisation check (LLM-judged).

Answers:
  AI-CO-01  Match model choice to cost/quality needs

Signals:
  * system.serving.endpoint_usage – endpoint names and request volumes (last 30 d)
    hint at which models are in use and how heavily each is exercised.
  * system.billing.usage – GPU vs CPU serving SKU distribution gives a first-order
    read on whether premium compute is the default.

Limitation: whether a model is cost/quality-optimal for a given use case requires
knowledge of the use-case requirements; system tables cannot provide that.  The LLM
judge is asked to weigh observable evidence and flag patterns that warrant manual review.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_WINDOW_DAYS = 30

_ENDPOINT_SQL = (
    "SELECT se.endpoint_name AS endpoint_name, COUNT(*) AS request_count "
    "FROM system.serving.endpoint_usage eu "
    "JOIN system.serving.served_entities se "
    "ON eu.served_entity_id = se.served_entity_id "
    f"WHERE eu.request_time >= current_timestamp() - INTERVAL {_WINDOW_DAYS} DAYS "
    "GROUP BY se.endpoint_name "
    "ORDER BY request_count DESC "
    "LIMIT 20"
)

_SKU_SQL = (
    "SELECT sku_name, SUM(usage_quantity) AS dbu "
    "FROM system.billing.usage "
    f"WHERE usage_date >= current_date() - INTERVAL {_WINDOW_DAYS} DAYS "
    "AND sku_name ILIKE '%SERVING%' "
    "GROUP BY sku_name "
    "ORDER BY dbu DESC "
    "LIMIT 20"
)

_NOTE = (
    "Model-choice appropriateness — whether a cheaper model could satisfy a given "
    "use case — cannot be determined from system tables alone; this assessment is "
    "based on observable endpoint names and serving SKU patterns only."
)

_REF = "https://docs.databricks.com/en/machine-learning/model-serving/index.html"


@register(layer="ai", question_ids=["AI-CO-01"])
class ModelChoiceCheck(Check):
    """Assess model-choice cost optimisation.

    Collects active serving endpoint names and request volumes, plus the billing
    SKU breakdown for serving compute.  Both are proxies; the LLM judge weighs them
    and flags patterns that suggest an opportunity to right-size model choice.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        endpoint_rows = ctx.sql.query(_ENDPOINT_SQL)
        sku_rows = ctx.sql.query(_SKU_SQL)

        if endpoint_rows:
            endpoint_summary = (
                f"{len(endpoint_rows)} serving endpoints active in the last "
                f"{_WINDOW_DAYS} days; top endpoints: "
                + ", ".join(
                    f"{r['endpoint_name']} ({r['request_count']} reqs)"
                    for r in endpoint_rows[:5]
                )
            )
        else:
            endpoint_summary = (
                f"No serving endpoint usage found in the last {_WINDOW_DAYS} days"
            )

        if sku_rows:
            sku_summary = (
                f"Serving billing SKUs (last {_WINDOW_DAYS} d): "
                + ", ".join(
                    f"{r['sku_name']} ({r['dbu']} DBU)" for r in sku_rows[:5]
                )
            )
        else:
            sku_summary = (
                f"No serving billing usage found in the last {_WINDOW_DAYS} days"
            )

        return [
            Evidence(
                kind="sql",
                summary=endpoint_summary,
                detail=_ENDPOINT_SQL,
                rows=endpoint_rows[:20],
                ref=_REF,
            ),
            Evidence(
                kind="sql",
                summary=sku_summary,
                detail=_SKU_SQL,
                rows=sku_rows[:10],
                ref=_REF,
            ),
            Evidence(
                kind="note",
                summary=_NOTE,
                ref=_REF,
            ),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
