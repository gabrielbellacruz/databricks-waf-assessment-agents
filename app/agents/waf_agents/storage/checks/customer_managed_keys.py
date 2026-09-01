"""Customer-managed keys (CMK / BYOK) check (LLM-judged).

Answers:
  STO-SCP-02  Use customer-managed keys where required

CMK configuration is a workspace/account-level setting managed via the
Databricks account console or cloud-provider APIs.  It is NOT exposed via the
agent's service principal in workspace system tables.

This check collects the best available proxy signals (storage credential and
external location counts give a rough governance-maturity indication) and
clearly states the visibility limitation in a note evidence item so the LLM
judge can correctly return ``unknown`` with low confidence — the honest outcome
when the actual setting is not observable.  A high storage-credential and
external-location count suggests an organised storage layer, which mildly
correlates with maturity that might include CMK, but the correlation is very
weak; it does not confirm CMK is enabled.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_STORAGE_CREDS_SQL = (
    "SELECT COUNT(*) AS storage_credential_count"
    " FROM system.information_schema.storage_credentials"
)

_EXT_LOCATIONS_SQL = (
    "SELECT COUNT(*) AS external_location_count"
    " FROM system.information_schema.external_locations"
)

_CMK_NOTE = (
    "Customer-managed key (CMK / BYOK) configuration is a workspace/account-level setting "
    "managed via the Databricks account console or cloud provider APIs. It is NOT exposed in "
    "workspace system tables visible to the agent's service principal. This check cannot "
    "determine whether CMK is enabled; storage credential and external location counts are "
    "collected only as weak governance-maturity context. Admin confirmation is required to "
    "verify CMK posture. "
    "Ref: https://docs.databricks.com/en/security/keys/customer-managed-keys.html"
)

_REF = "https://docs.databricks.com/en/security/keys/customer-managed-keys.html"


@register(layer="storage", question_ids=["STO-SCP-02"])
class CustomerManagedKeysCheck(Check):
    """Assess customer-managed key usage for storage encryption.

    CMK/BYOK status is a workspace/account-level setting not visible in
    system tables. Evidence is limited to weak proxy counts (storage
    credentials and external locations) plus a dominant note that records the
    visibility limitation. The LLM judge is expected to return ``unknown`` with
    a ``low`` confidence rating; that is the correct and honest outcome given
    the absence of observable signal.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        cred_rows = ctx.sql.query(_STORAGE_CREDS_SQL)
        ext_rows = ctx.sql.query(_EXT_LOCATIONS_SQL)

        cred_count = int(
            (cred_rows[0].get("storage_credential_count") or 0) if cred_rows else 0
        )
        ext_count = int((ext_rows[0].get("external_location_count") or 0) if ext_rows else 0)

        proxy_evidence = Evidence(
            kind="sql",
            summary=(
                f"{cred_count} storage credential(s) and {ext_count} external location(s) "
                "registered; storage-governance maturity proxy only — CMK status is NOT "
                "observable from this data"
            ),
            detail=_STORAGE_CREDS_SQL + " ; " + _EXT_LOCATIONS_SQL,
            rows=(cred_rows[:5] + ext_rows[:5]),
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_CMK_NOTE,
            rows=[],
            ref=_REF,
        )
        return [proxy_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
