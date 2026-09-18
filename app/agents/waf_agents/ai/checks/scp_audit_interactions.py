"""AI interaction audit check (LLM-judged).

Answers:
  AI-SCP-05  Audit AI interactions

Signals:
1. ``system.ai_gateway.usage``: row count over the last 30 days — the presence
   of rows confirms that AI Gateway is logging interactions (input, output,
   requester, status, guardrail events) to an auditable system table.
2. ``system.access.audit``: serving-endpoint query events (``queryServingEndpoint``,
   ``invokeServingEndpoint``) — confirms that direct (non-gateway) AI calls are
   also captured in the platform audit trail.

The audit table coverage is treated as largely deterministic: if
``system.ai_gateway.usage`` has rows and ``system.access.audit`` has serving
query events, interactions are being logged.  The LLM judge contextualises
whether the volume and coverage meet the spirit of the WAF requirement.

Limitations noted:
- Audit *review* (whether anyone reads the logs) and retention configuration
  are not observable from system tables.
- Only AI Gateway-routed calls appear in system.ai_gateway.usage; direct calls
  appear in system.access.audit but with less detail.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_GATEWAY_AUDIT_SQL = """\
SELECT
  COUNT(*) AS total_logged_calls,
  COUNT(DISTINCT endpoint_name) AS distinct_endpoints,
  COUNT(DISTINCT requester) AS distinct_requesters,
  MIN(event_time) AS earliest_log,
  MAX(event_time) AS latest_log
FROM system.ai_gateway.usage
WHERE event_time >= current_timestamp() - INTERVAL 30 DAYS\
"""

_SERVING_AUDIT_SQL = """\
SELECT action_name,
       COUNT(*) AS event_count
FROM system.access.audit
WHERE service_name IN ('serving', 'mlflowEndpoints', 'mlflowAcledArtifact')
  AND action_name IN (
      'queryServingEndpoint', 'invokeServingEndpoint',
      'createServingEndpoint', 'updateServingEndpoint'
  )
  AND event_date >= current_date() - INTERVAL 30 DAYS
GROUP BY action_name
ORDER BY event_count DESC\
"""

_NOTE = (
    "system.ai_gateway.usage provides per-request audit records (requester, endpoint, "
    "tokens, status, guardrail events) for all AI Gateway-routed traffic; its presence "
    "confirms interaction-level auditing for that path. "
    "system.access.audit captures serving endpoint invocation events for all traffic "
    "but with less detail than the gateway log. "
    "However: (1) audit log *review* processes and alerting are not observable; "
    "(2) retention settings (how long logs are kept) are not surfaced in system tables; "
    "(3) AI applications that write directly to serving endpoints without going through "
    "AI Gateway have coarser audit coverage. A reviewer must confirm log review cadence and "
    "retention meet compliance requirements."
)

_REF = "https://docs.databricks.com/en/admin/system-tables/audit.html"


@register(layer="ai", question_ids=["AI-SCP-05"])
class AuditInteractionsCheck(Check):
    """Assess AI interaction auditing via AI Gateway usage logs and serving audit events.

    Evidence:
    - system.ai_gateway.usage: logged call count, distinct endpoints and requesters
      (presence = interaction-level auditing is active for gateway traffic).
    - system.access.audit: serving endpoint invocation event counts.
    A note records log-review and retention limitations.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        gateway_rows = ctx.sql.query(_GATEWAY_AUDIT_SQL)
        serving_rows = ctx.sql.query(_SERVING_AUDIT_SQL)

        if gateway_rows:
            g = gateway_rows[0]
            total_logged = int(g.get("total_logged_calls") or 0)
            distinct_endpoints = int(g.get("distinct_endpoints") or 0)
            distinct_requesters = int(g.get("distinct_requesters") or 0)

            if total_logged > 0:
                gateway_summary = (
                    f"AI Gateway: {total_logged} interaction(s) logged across "
                    f"{distinct_endpoints} endpoint(s) and {distinct_requesters} distinct "
                    "requester(s) in system.ai_gateway.usage (last 30 days) — "
                    "interaction-level auditing is active for gateway-routed traffic"
                )
            else:
                gateway_summary = (
                    "No AI Gateway interactions logged in system.ai_gateway.usage "
                    "for the last 30 days — gateway-level audit trail is absent or "
                    "no gateway traffic exists"
                )
        else:
            total_logged = distinct_endpoints = distinct_requesters = 0
            gateway_summary = "No rows in system.ai_gateway.usage for the last 30 days"

        gateway_evidence = Evidence(
            kind="sql",
            summary=gateway_summary,
            detail=_GATEWAY_AUDIT_SQL,
            rows=[{
                "total_logged_calls": total_logged,
                "distinct_endpoints": distinct_endpoints,
                "distinct_requesters": distinct_requesters,
            }],
            ref="https://docs.databricks.com/en/ai-gateway/index.html",
        )

        total_serving_events = sum(int(r.get("event_count") or 0) for r in serving_rows)
        if total_serving_events > 0:
            serving_summary = (
                f"{total_serving_events} serving-endpoint invocation/management event(s) "
                f"across {len(serving_rows)} distinct action type(s) in "
                "system.access.audit (last 30 days)"
            )
        else:
            serving_summary = (
                "No serving-endpoint invocation events found in "
                "system.access.audit for the last 30 days"
            )

        serving_evidence = Evidence(
            kind="sql",
            summary=serving_summary,
            detail=_SERVING_AUDIT_SQL,
            rows=serving_rows,
            ref=_REF,
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [gateway_evidence, serving_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
