"""Load the canonical WAF question set at runtime.

Single source of truth is repo-root ``/data/waf-data.json`` (the frontend copies
it into public/ at build; the DAB syncs it to the Job). The agent never carries
its own question list, so adding a question is a data change, not a code change.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from waf_agents.core.models import Question

# Overridable so the Job can point at the file location it was synced to.
_ENV_VAR = "WAF_DATA_PATH"


def _packaged_path() -> Path:
    # Copied into the package at wheel-build time (scripts/bundle_data.py). This
    # is what the installed wheel uses inside the Job.
    return Path(__file__).resolve().parent.parent / "data" / "waf-data.json"


def _repo_path() -> Path:
    # Local dev / editable installs: the canonical file at repo-root /data.
    # agents/waf_agents/core/questions.py -> repo root is three parents up.
    return Path(__file__).resolve().parents[3] / "data" / "waf-data.json"


def data_path() -> Path:
    override = os.environ.get(_ENV_VAR)
    if override:
        return Path(override)
    packaged = _packaged_path()
    return packaged if packaged.exists() else _repo_path()


def _checklist(question: dict) -> list[str]:
    guidance = question.get("databricksGuidance") or {}
    out: list[str] = []
    for group in guidance.get("validationChecklist", []) or []:
        out.extend(group.get("questions", []) or [])
    return out


def load_questions(layer: str, path: Path | None = None) -> list[Question]:
    """Return every question in ``layer`` (a category id like 'ingestion'),
    flattened across its pillars, in file order."""
    raw = json.loads((path or data_path()).read_text())
    categories = raw if isinstance(raw, list) else raw.get("categories", [])
    category = next((c for c in categories if c.get("id") == layer), None)
    if category is None:
        raise ValueError(f"layer {layer!r} not found in question set")

    questions: list[Question] = []
    for pillar in category.get("pillars", []):
        for q in pillar.get("questions", []):
            questions.append(
                Question(
                    id=q["id"],
                    pillar_id=pillar["id"],
                    title=q.get("title", ""),
                    principle=q.get("principle", ""),
                    details=q.get("details"),
                    checklist=_checklist(q),
                )
            )
    return questions
