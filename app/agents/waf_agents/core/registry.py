"""Check base class and the question -> check registry.

The registry is the mechanism that keeps questions *out of code*: a check
declares which question ids it can answer, and the agent looks checks up by the
ids it finds in the canonical question set at runtime. A question with no
registered check degrades gracefully to an ``unassessed`` finding.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Evidence, Finding, Question

# question_id -> Check subclass. One check may answer several questions; each
# question maps to at most one check (last registration wins, logged in tests).
CHECK_REGISTRY: dict[str, type[Check]] = {}


class Check(ABC):
    """A single automated check. ``collect`` gathers evidence deterministically;
    ``judge`` turns evidence + the question into a Finding. Keeping them separate
    makes evidence explainable and both halves independently testable."""

    layer: str = ""
    question_ids: tuple[str, ...] = ()

    @abstractmethod
    def collect(self, ctx: AgentContext) -> list[Evidence]: ...

    @abstractmethod
    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding: ...

    def run(self, question: Question, ctx: AgentContext) -> Finding:
        return self.judge(self.collect(ctx), question, ctx)


def register(layer: str, question_ids: list[str]):
    """Class decorator: bind a check to a layer and the question ids it answers."""

    def deco(cls: type[Check]) -> type[Check]:
        cls.layer = layer
        cls.question_ids = tuple(question_ids)
        for qid in question_ids:
            CHECK_REGISTRY[qid] = cls
        return cls

    return deco


def check_for(question_id: str) -> type[Check] | None:
    return CHECK_REGISTRY.get(question_id)
