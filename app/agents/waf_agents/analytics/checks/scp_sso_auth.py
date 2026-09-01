"""SSO authentication check for analytics users (LLM-judged).

Answers:
  ANA-SCP-01  Authenticate analytics users via SSO

SSO and SCIM configuration is workspace-level and not fully observable via
system tables. The observable proxy is the login-event distribution from
system.access.audit (last 30 days): the share of SAML/OIDC logins vs password
and token logins indicates whether SSO is in active use. A note records that
SCIM group-sync enforcement requires manual confirmation.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_LOGIN_SQL = """\
SELECT action_name,
       COUNT(*) AS event_count
FROM system.access.audit
WHERE event_time >= current_timestamp() - INTERVAL 30 DAYS
  AND action_name IN (
        'workspaceLogin', 'tokenLogin',
        'samlLogin', 'oidcLogin', 'passwordLogin'
  )
GROUP BY action_name\
"""

_SSO_ACTIONS = frozenset({"samlLogin", "oidcLogin", "samllogin", "oidclogin"})

_SSO_NOTE = (
    "SSO/SCIM identity-provider configuration is workspace-level and cannot be read directly "
    "from system tables. Login event distribution from system.access.audit (SAML/OIDC vs "
    "password/token logins) is used as a proxy for SSO adoption. Manual confirmation of SSO "
    "enforcement and SCIM group sync is recommended."
)

_REF = "https://docs.databricks.com/en/administration-guide/users-groups/scim/index.html"


@register(layer="analytics", question_ids=["ANA-SCP-01"])
class SsoAuthCheck(Check):
    """Assess SSO adoption via login-event distribution from system.access.audit.

    A second note evidence records that SCIM configuration and enforcement of
    SSO-only access cannot be observed from system tables alone.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_LOGIN_SQL)

        sso_logins = 0
        non_sso_logins = 0
        for row in rows:
            action = str(row.get("action_name") or "").lower()
            count = int(row.get("event_count") or 0)
            if action in ("samllogin", "oidclogin"):
                sso_logins += count
            else:
                non_sso_logins += count

        total_logins = sso_logins + non_sso_logins

        if total_logins > 0:
            sso_pct = round(100.0 * sso_logins / total_logins, 1)
            summary = (
                f"{sso_logins} of {total_logins} login events in the last 30 days used "
                f"SSO (SAML/OIDC) — {sso_pct}%"
            )
        else:
            summary = (
                "No login audit events found in system.access.audit for the last 30 days"
            )

        return [
            Evidence(
                kind="sql",
                summary=summary,
                detail=_LOGIN_SQL,
                rows=rows[:20],
                ref="https://docs.databricks.com/en/monitoring/system-tables/audit.html",
            ),
            Evidence(
                kind="note",
                summary=_SSO_NOTE,
                rows=[],
                ref=_REF,
            ),
        ]

    def judge(
        self, evidence: list[Evidence], question: Question, ctx: AgentContext
    ) -> Finding:
        return judge_with_llm(ctx, question, evidence)
