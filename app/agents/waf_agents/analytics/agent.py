"""Analytics layer agent.

Overrides ``discover_scope`` to determine which catalogs the checks run against:
the catalogs passed in, or every catalog the principal can see - the same
starting point the ingestion and storage agents use.
"""

from __future__ import annotations

# Importing the checks package runs each check's @register decorator.
from waf_agents.analytics import checks as _checks  # noqa: F401
from waf_agents.core.base import WafAgent
from waf_agents.core.clients import AgentContext
from waf_agents.core.factory import agent
from waf_agents.core.models import Scope


@agent("analytics")
class AnalyticsAgent(WafAgent):
    layer = "analytics"

    def discover_scope(self, ctx: AgentContext) -> Scope:
        catalogs = list(ctx.catalogs)
        if not catalogs:
            rows = ctx.sql.query(
                "SELECT catalog_name FROM system.information_schema.catalogs "
                "WHERE catalog_name <> 'hive_metastore'"
            )
            catalogs = [r["catalog_name"] for r in rows]
        return Scope(catalogs=catalogs)
