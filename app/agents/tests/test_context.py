from __future__ import annotations

from waf_agents.core import context as ctxmod
from waf_agents.core.context import build_architecture_context


class _FakeStore:
    """Duck-typed stand-in for ResultsStore: only the two read methods the
    context builder uses. ``files`` maps a volume path to bytes."""

    def __init__(self, rows, files=None, raise_on_fetch=False):
        self._rows = rows
        self._files = files or {}
        self._raise = raise_on_fetch

    def fetch_documents(self, assessment_id):
        if self._raise:
            raise RuntimeError("db down")
        return self._rows

    def read_volume_file(self, path):
        return self._files[path]


def test_text_docs_are_concatenated_with_filenames():
    store = _FakeStore(
        [
            {"filename": "design.md", "kind": "text", "extracted_text": "alpha"},
            {"filename": "notes.txt", "kind": "text", "extracted_text": "beta"},
        ]
    )
    arch = build_architecture_context(store, "a1")
    assert arch is not None
    assert "design.md" in arch.text and "alpha" in arch.text
    assert "notes.txt" in arch.text and "beta" in arch.text
    assert arch.images == []


def test_images_are_downloaded_and_capped():
    rows = [
        {"filename": "d.png", "kind": "image", "content_type": "image/png",
         "volume_path": "/Volumes/c/s/v/d.png"},
        {"filename": "big.png", "kind": "image", "content_type": "image/png",
         "volume_path": "/Volumes/c/s/v/big.png"},
    ]
    files = {
        "/Volumes/c/s/v/d.png": b"small",
        "/Volumes/c/s/v/big.png": b"x" * (ctxmod._MAX_IMAGE_BYTES + 1),  # over cap
    }
    arch = build_architecture_context(_FakeStore(rows, files), "a1")
    assert arch is not None
    # The oversized image is skipped; the small one is kept.
    assert arch.images == [("image/png", b"small")]


def test_image_count_is_capped(monkeypatch):
    monkeypatch.setattr(ctxmod, "_MAX_IMAGES", 2)
    rows = [
        {"filename": f"{i}.png", "kind": "image", "content_type": "image/png",
         "volume_path": f"/v/{i}.png"}
        for i in range(5)
    ]
    files = {f"/v/{i}.png": b"data" for i in range(5)}
    arch = build_architecture_context(_FakeStore(rows, files), "a1")
    assert arch is not None
    assert len(arch.images) == 2


def test_text_is_truncated_at_cap(monkeypatch):
    monkeypatch.setattr(ctxmod, "_MAX_TEXT_CHARS", 20)
    store = _FakeStore(
        [{"filename": "big.md", "kind": "text", "extracted_text": "z" * 100}]
    )
    arch = build_architecture_context(store, "a1")
    assert arch is not None
    assert "truncated" in arch.text


def test_doc_and_image_names_and_summary_are_populated():
    rows = [
        {"filename": "design.md", "kind": "text", "extracted_text": "alpha"},
        {"filename": "diagram.png", "kind": "image", "content_type": "image/png",
         "volume_path": "/v/diagram.png"},
    ]
    arch = build_architecture_context(
        _FakeStore(rows, {"/v/diagram.png": b"img"}), "a1"
    )
    assert arch is not None
    assert arch.doc_names == ["design.md"]
    assert arch.image_names == ["diagram.png"]
    summary = arch.summary()
    assert "design.md" in summary and "diagram.png" in summary


def test_no_rows_returns_none():
    assert build_architecture_context(_FakeStore([]), "a1") is None


def test_fetch_failure_returns_none():
    assert build_architecture_context(_FakeStore([], raise_on_fetch=True), "a1") is None


def test_image_only_that_is_unreadable_yields_none():
    # One image row, but the download fails -> no text, no images -> None.
    rows = [
        {"filename": "d.png", "kind": "image", "content_type": "image/png",
         "volume_path": "/missing"}
    ]
    arch = build_architecture_context(_FakeStore(rows, files={}), "a1")
    assert arch is None
