"""Agent factory / registry.

Adding a new layer agent is: subclass ``WafAgent``, decorate it with
``@agent("<layer>")``, and register its checks. The factory then builds and
returns its compiled graph by layer id - nothing else needs to change.
"""

from __future__ import annotations

from waf_agents.core.base import WafAgent

# layer id -> WafAgent subclass
AGENTS: dict[str, type[WafAgent]] = {}


def agent(layer: str):
    """Class decorator registering a layer agent under its layer id."""

    def deco(cls: type[WafAgent]) -> type[WafAgent]:
        cls.layer = layer
        AGENTS[layer] = cls
        return cls

    return deco


def create_agent(layer: str) -> WafAgent:
    try:
        return AGENTS[layer]()
    except KeyError:
        raise ValueError(
            f"no agent registered for layer {layer!r}; known: {list_agents()}"
        ) from None


def build_agent_graph(layer: str):
    """Compiled LangGraph for a layer."""
    return create_agent(layer).build_graph()


def list_agents() -> list[str]:
    return sorted(AGENTS)
