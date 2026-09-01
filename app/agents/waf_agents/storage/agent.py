"""Storage layer agent.

Overrides ``discover_scope`` to determine which catalogs the checks run against.
Deeper inventory (curated/gold tables, external locations backing the storage
layer) can land later; for now scope is the catalogs passed in, or every catalog
the principal can see - the same starting point the ingestion agent uses.
"""

from __future__ import annotations

from waf_agents.core.base import WafAgent
from waf_agents.core.clients import AgentContext
from waf_agents.core.factory import agent
from waf_agents.core.models import Scope

# Importing the checks package runs each check's @register decorator.
from waf_agents.storage import checks as _checks  # noqa: F401


@agent("storage")
class StorageAgent(WafAgent):
    layer = "storage"

    def discover_scope(self, ctx: AgentContext) -> Scope:
        catalogs = list(ctx.catalogs)
        if not catalogs:
            rows = ctx.sql.query(
                "SELECT catalog_name FROM system.information_schema.catalogs "
                "WHERE catalog_name <> 'hive_metastore'"
            )
            catalogs = [r["catalog_name"] for r in rows]
        return Scope(catalogs=catalogs)
