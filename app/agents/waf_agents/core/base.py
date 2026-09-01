"""The reusable agent skeleton every layer shares.

``WafAgent`` builds the LangGraph workflow:

    START -> load_questions -> discover_scope -> run_checks -> END

A concrete layer agent (e.g. IngestionAgent) supplies ``layer`` and overrides
``discover_scope``; its checks are registered separately and found by question
id. Persistence and progress are injected via the run config so this module
carries no Lakebase or Databricks dependency and stays unit-testable.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Finding, Scope, Verdict
from waf_agents.core.questions import load_questions
from waf_agents.core.registry import check_for
from waf_agents.core.state import AgentState

# Optional callback the Job passes to stream progress into agent_runs.
ProgressFn = Callable[[int, int], None]


class WafAgent:
    """Base layer agent. Subclasses set ``layer`` (via the ``@agent`` decorator)
    and may override ``discover_scope``; the graph assembly is inherited."""

    layer: str = ""

    # --- layer hook -----------------------------------------------------
    def discover_scope(self, ctx: AgentContext) -> Scope:
        """Build the layer's object inventory so checks are scoped to the layer
        rather than to workspace-global metrics. Default: just the catalogs in
        scope; layer agents override with real discovery."""
        return Scope(catalogs=list(ctx.catalogs))

    # --- graph nodes ----------------------------------------------------
    def _load_questions(self, state: AgentState, config: RunnableConfig) -> AgentState:
        questions = load_questions(self.layer)
        return {"questions": questions, "n_total": len(questions), "n_done": 0}

    def _discover_scope(self, state: AgentState, config: RunnableConfig) -> AgentState:
        ctx: AgentContext = config["configurable"]["ctx"]
        return {"scope": self.discover_scope(ctx)}

    def _run_checks(self, state: AgentState, config: RunnableConfig) -> AgentState:
        ctx: AgentContext = config["configurable"]["ctx"]
        ctx.scope = state.get("scope")
        progress: ProgressFn | None = config["configurable"].get("progress")
        questions = state["questions"]

        findings: list[Finding] = []
        for i, q in enumerate(questions, start=1):
            check_cls = check_for(q.id)
            if check_cls is None:
                findings.append(Finding.unassessed(q.id, q.pillar_id))
            else:
                try:
                    findings.append(check_cls().run(q, ctx))
                except Exception as exc:  # a broken check must not fail the run
                    findings.append(
                        Finding(
                            question_id=q.id,
                            pillar_id=q.pillar_id,
                            verdict=Verdict.UNKNOWN,
                            confidence=Confidence.NONE,
                            rationale=f"Check errored and was skipped: {exc}",
                            auto_assessable=False,
                        )
                    )
            if progress is not None:
                progress(i, len(questions))
        return {"findings": findings, "n_done": len(questions)}

    # --- assembly -------------------------------------------------------
    def build_graph(self):
        g = StateGraph(AgentState)
        g.add_node("load_questions", self._load_questions)
        g.add_node("discover_scope", self._discover_scope)
        g.add_node("run_checks", self._run_checks)
        g.add_edge(START, "load_questions")
        g.add_edge("load_questions", "discover_scope")
        g.add_edge("discover_scope", "run_checks")
        g.add_edge("run_checks", END)
        return g.compile()

    def run(self, ctx: AgentContext, progress: ProgressFn | None = None) -> list[Finding]:
        """Convenience entry: run the whole graph and return the findings."""
        final = self.build_graph().invoke(
            {"assessment_id": ctx.assessment_id, "layer": self.layer},
            config={"configurable": {"ctx": ctx, "progress": progress}},
        )
        return final["findings"]
