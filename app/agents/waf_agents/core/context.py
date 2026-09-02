"""Gather the assessment's uploaded architecture documentation for a run.

The backend stores each uploaded file in a UC Volume and a metadata row in
Lakebase (extracted text inline for text formats; images stored as bytes). This
module reads those rows once per run via the results store and assembles an
:class:`ArchitectureContext` that every LLM-judged check shares (see
``core.llm.judge_with_llm``):

  * text from pdf/txt/md/docx uploads is concatenated and size-capped, then
    inlined into the judge prompt;
  * image uploads are downloaded from the Volume and passed to the model as
    vision blocks (capped in count and per-file size to bound prompt cost).

Best-effort: any failure returns None so a storage hiccup never fails a run -
the checks then behave exactly as they did before uploads existed.
"""

from __future__ import annotations

from waf_agents.core.clients import ArchitectureContext, DocImage
from waf_agents.core.store import ResultsStore

# Caps so a large upload set can't blow up the prompt or the API budget.
_MAX_TEXT_CHARS = 60_000
_MAX_IMAGES = 6
_MAX_IMAGE_BYTES = 4 * 1024 * 1024  # 4 MB per image


def build_architecture_context(
    store: ResultsStore, assessment_id: str
) -> ArchitectureContext | None:
    """Assemble the uploaded-docs context for an assessment, or None if there is
    nothing usable (no uploads, or storage unavailable)."""
    try:
        rows = store.fetch_documents(assessment_id)
    except Exception:
        return None
    if not rows:
        return None

    text_parts: list[str] = []
    doc_names: list[str] = []
    images: list[DocImage] = []
    image_names: list[str] = []
    for row in rows:
        if row.get("kind") == "image":
            if len(images) >= _MAX_IMAGES:
                continue
            try:
                data = store.read_volume_file(row["volume_path"])
            except Exception:
                continue
            if data and len(data) <= _MAX_IMAGE_BYTES:
                images.append((row.get("content_type") or "image/png", data))
                image_names.append(row.get("filename") or "diagram")
        else:
            body = (row.get("extracted_text") or "").strip()
            if body:
                filename = row.get("filename", "document")
                text_parts.append(f"## {filename}\n{body}")
                doc_names.append(filename)

    text = "\n\n".join(text_parts)
    if len(text) > _MAX_TEXT_CHARS:
        text = text[:_MAX_TEXT_CHARS] + "\n\n[architecture documentation truncated]"

    ctx = ArchitectureContext(
        text=text, images=images, doc_names=doc_names, image_names=image_names
    )
    return ctx if ctx else None
