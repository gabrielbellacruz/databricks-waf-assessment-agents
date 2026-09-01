"""LangGraph state for a layer agent run.

State is intentionally plain data (questions, scope, findings, progress). The
execution clients live in the run ``config`` (see ``clients.AgentContext``), not
in state, so state stays inspectable and checkpointable.
"""

from __future__ import annotations

from typing import TypedDict

from waf_agents.core.models import Finding, Question, Scope


class AgentState(TypedDict, total=False):
    assessment_id: str
    layer: str
    questions: list[Question]
    scope: Scope | None
    findings: list[Finding]
    n_total: int
    n_done: int
