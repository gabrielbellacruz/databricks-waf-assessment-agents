"""Turn an uploaded architecture document into text the agents can read.

Text formats (pdf/txt/md/docx) are extracted here at upload time and stored on
the row, so the agents (and the UI) never re-parse the file. Images are not
extracted - they are sent to the LLM judge as vision blocks at run time - so
``kind_for`` classifies them as ``image`` and ``extract_text`` returns "".

Dependency-light on purpose (this backend avoids native wheels for the flaky
Apps build proxy): only ``pypdf`` is added (pure-Python). ``.docx`` is a zip of
XML, so it is parsed with the stdlib rather than pulling in python-docx/lxml.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile

# Extensions we accept, split by how the agent consumes them.
TEXT_EXTENSIONS = (".pdf", ".txt", ".md", ".markdown", ".docx")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS + IMAGE_EXTENSIONS

# WordprocessingML namespace: paragraph <w:p> / text run <w:t> live here.
_DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _ext(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""


def is_allowed(filename: str) -> bool:
    return _ext(filename) in ALLOWED_EXTENSIONS


def kind_for(filename: str) -> str:
    """``image`` for formats sent to the model as vision, else ``text``."""
    return "image" if _ext(filename) in IMAGE_EXTENSIONS else "text"


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader  # pure-Python; imported lazily

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            # A malformed page shouldn't lose the rest of the document.
            continue
    return "\n\n".join(p.strip() for p in pages if p.strip())


def _extract_docx(data: bytes) -> str:
    # A .docx is a zip; the body text is in word/document.xml as <w:p>/<w:t>.
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        with zf.open("word/document.xml") as f:
            tree = ET.parse(f)
    paragraphs = []
    for para in tree.iter(f"{_DOCX_NS}p"):
        text = "".join(node.text or "" for node in para.iter(f"{_DOCX_NS}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from a supported text document. Returns "" for images
    or when extraction yields nothing. Never raises - a parse failure degrades to
    empty text so the upload still succeeds (the file is stored regardless)."""
    ext = _ext(filename)
    try:
        if ext == ".pdf":
            return _extract_pdf(data)
        if ext == ".docx":
            return _extract_docx(data)
        if ext in (".txt", ".md", ".markdown"):
            return data.decode("utf-8", errors="replace")
    except Exception:
        return ""
    return ""
