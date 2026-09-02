"""LLM-judged verdicts for questions with no clean numeric signal.

A deterministic check computes a ratio and thresholds it. Many WAF questions
have no such single number - the honest answer comes from weighing several
configuration artifacts (job/pipeline/cluster settings, external locations,
source control, ...) the way a reviewer would. Those checks gather that evidence
in ``collect`` and call :func:`judge_with_llm` here, which asks a Databricks
serving-endpoint model to return a structured verdict from the evidence alone.

Design rules that keep this trustworthy:
  * The model judges ONLY the evidence passed in - the prompt forbids inventing
    facts. No evidence -> it must answer ``unknown``.
  * Output is strict JSON we parse; anything unparseable degrades to ``unknown``
    rather than guessing.
  * Confidence is capped at ``medium``: an LLM reading proxies is never as sure
    as a deterministic system-table count (which uses ``high``).
  * With no ``llm`` wired (local/offline), the check returns ``unassessed`` so
    runs and unit tests work without a workspace.
"""

from __future__ import annotations

import json

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict

_VALID_VERDICTS = {v.value for v in Verdict}
# The LLM never claims more than medium confidence - see module docstring.
_VALID_CONFIDENCE = {Confidence.MEDIUM.value, Confidence.LOW.value}

_SYSTEM_PROMPT = (
    "You are a Databricks Well-Architected Framework reviewer. You are given ONE "
    "best-practice question and a bundle of EVIDENCE collected from a customer's "
    "Databricks workspace (system-table rows and configuration artifacts), and "
    "sometimes ARCHITECTURE DOCUMENTATION the customer uploaded (design docs and "
    "diagrams). Decide how well the workspace meets the best practice, using ONLY "
    "the evidence provided - never assume facts that are not present. The uploaded "
    "documentation is valid evidence, but describes intent and may be out of date, "
    "so weigh it below hard signals from the workspace when the two disagree.\n\n"
    "Verdicts:\n"
    "  met      - the evidence clearly shows the practice is followed\n"
    "  partial  - followed in some places / to some degree\n"
    "  not_met  - the evidence shows it is not followed\n"
    "  unknown  - the evidence is insufficient to judge (use this freely)\n\n"
    "Confidence is 'medium' when the evidence is a strong proxy, 'low' when it is "
    "weak or indirect. If evidence is empty or irrelevant, answer verdict "
    "'unknown' with confidence 'low'.\n\n"
    "Respond with ONLY a JSON object, no prose, no code fences:\n"
    '{"verdict": "met|partial|not_met|unknown", "confidence": "medium|low", '
    '"score": null, "rationale": "one or two sentences citing the evidence"}\n'
    "When (and only when) you relied on uploaded architecture documentation, also "
    'include a "doc_references" array so a reviewer can find what you used - see '
    "the per-question instructions for its shape."
)


def _evidence_block(evidence: list[Evidence]) -> str:
    if not evidence:
        return "(no evidence was collected)"
    parts = []
    for i, e in enumerate(evidence, start=1):
        line = f"[{i}] ({e.kind}) {e.summary}"
        if e.rows:
            # Bound the rows we serialize so a big estate can't blow the prompt.
            line += "\n    rows: " + json.dumps(e.rows[:25], default=str)
        if e.detail:
            line += f"\n    detail: {e.detail[:500]}"
        parts.append(line)
    return "\n".join(parts)


def build_user_prompt(question: Question, evidence: list[Evidence]) -> str:
    """The per-question user message: the question, its guidance, and evidence."""
    lines = [
        f"QUESTION ({question.id}): {question.title}",
    ]
    if question.principle:
        lines.append(f"Principle: {question.principle}")
    if question.details:
        lines.append(f"Details: {question.details[:800]}")
    if question.checklist:
        lines.append("Checklist:\n" + "\n".join(f"  - {c}" for c in question.checklist))
    lines.append("\nEVIDENCE:\n" + _evidence_block(evidence))
    return "\n".join(lines)


def _parse(text: str) -> dict | None:
    """Extract the JSON object from the model's reply; None if unparseable."""
    s = text.strip()
    if s.startswith("```"):
        # strip a ```json ... ``` fence if the model added one
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        obj = json.loads(s[start : end + 1])
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


# The judge may cite this many source snippets; keeps a runaway reply bounded.
_MAX_DOC_REFERENCES = 10
_MAX_QUOTE_CHARS = 300


def _doc_reference_instructions(arch) -> str:
    """The per-question ask for referenceable citations, listing the source names
    the judge may cite (## headings for text, filenames for diagrams)."""
    sources = list(arch.doc_names) + list(arch.image_names)
    names = ", ".join(sources) if sources else "the documents above"
    return (
        "\n\nIf your verdict used the ARCHITECTURE DOCUMENTATION above, add a "
        '"doc_references" array to your JSON. Each item is '
        '{"document": <source name>, "quote": <verbatim excerpt you relied on, '
        "copied EXACTLY so a reviewer can find it, <=200 chars>}. Cite by source "
        f"name (one of: {names}); for a diagram, set \"document\" to its filename "
        'and "quote" to a short description of what in it you used. Omit '
        '"doc_references" entirely if you did not use the documentation.'
    )


def _architecture_sources(arch, parsed: dict | None) -> list[Evidence]:
    """Evidence that makes the uploaded docs traceable: a marker of what was fed
    to the judge, plus any verbatim citations it said it used - each pointing at
    the source document (in ``ref``) with the excerpt (in ``detail``) so a
    reviewer can open that document and find it."""
    if not arch:
        return []
    out = [
        Evidence(
            kind="architecture_doc",
            summary=f"Architecture documentation provided to the judge ({arch.summary()}).",
            detail="Weighed below hard workspace signals; verify against the live system.",
        )
    ]
    refs = (parsed or {}).get("doc_references")
    if isinstance(refs, list):
        for ref in refs[:_MAX_DOC_REFERENCES]:
            if not isinstance(ref, dict):
                continue
            quote = str(ref.get("quote", "")).strip()
            if not quote:
                continue
            document = str(ref.get("document", "")).strip() or "document"
            out.append(
                Evidence(
                    kind="architecture_doc",
                    summary=f"Cited from uploaded documentation: {document}",
                    detail=quote[:_MAX_QUOTE_CHARS],
                    ref=document,
                )
            )
    return out


def judge_with_llm(
    ctx: AgentContext, question: Question, evidence: list[Evidence]
) -> Finding:
    """Ask the wired LLM to judge ``question`` from ``evidence`` and map its reply
    to a Finding. Falls back to ``unassessed`` when no LLM is available, and to a
    low-confidence ``unknown`` when the reply can't be parsed or is out of range.
    The collected evidence is always attached for explainability; when uploaded
    architecture docs fed the judge, traceable citations are attached too."""
    if ctx.llm is None:
        f = Finding.unassessed(question.id, question.pillar_id)
        f.sources = evidence
        return f

    user = build_user_prompt(question, evidence)
    images = None
    arch = ctx.architecture
    if arch:
        if arch.text:
            user += (
                "\n\nARCHITECTURE DOCUMENTATION (uploaded by the customer):\n"
                + arch.text
            )
        if arch.images:
            # Diagrams ride along as vision blocks; name them in the text too so a
            # text-only endpoint knows they exist and can cite them by filename.
            listed = ", ".join(arch.image_names) or f"{len(arch.images)} image(s)"
            user += (
                f"\n\n[Architecture diagram image(s) attached below as evidence: "
                f"{listed}.]"
            )
            images = list(arch.images)
        user += _doc_reference_instructions(arch)

    reply = ctx.llm.complete(_SYSTEM_PROMPT, user, images=images)
    parsed = _parse(reply)
    arch_sources = _architecture_sources(arch, parsed)
    if parsed is None:
        return Finding(
            question_id=question.id,
            pillar_id=question.pillar_id,
            verdict=Verdict.UNKNOWN,
            confidence=Confidence.LOW,
            rationale="LLM judge returned an unparseable response; needs manual review.",
            sources=evidence + arch_sources,
            auto_assessable=False,
        )

    verdict = str(parsed.get("verdict", "")).lower()
    confidence = str(parsed.get("confidence", "")).lower()
    if verdict not in _VALID_VERDICTS:
        verdict = Verdict.UNKNOWN.value
    # Cap at medium: an LLM reading proxies never gets 'high' (deterministic
    # counts do). A claimed 'high' is clamped down; anything unrecognized -> low.
    if confidence == Confidence.HIGH.value:
        confidence = Confidence.MEDIUM.value
    elif confidence not in _VALID_CONFIDENCE:
        confidence = Confidence.LOW.value

    score = parsed.get("score")
    if not isinstance(score, (int, float)):
        score = None

    return Finding(
        question_id=question.id,
        pillar_id=question.pillar_id,
        verdict=Verdict(verdict),
        confidence=Confidence(confidence),
        score=float(score) if score is not None else None,
        rationale=str(parsed.get("rationale", "")).strip()
        or "No rationale provided by the judge.",
        sources=evidence + arch_sources,
        auto_assessable=True,
    )
