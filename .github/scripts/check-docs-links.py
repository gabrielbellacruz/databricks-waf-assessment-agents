#!/usr/bin/env python3
"""Validate internal links across the docs/ site before it deploys.

The docs site is a set of self-contained HTML pages plus a shared stylesheet and
a nav script; there is no build step to catch a broken cross-page link or a
mistyped anchor. This script does: for every docs/**/*.html it checks that each
relative href/src resolves to a file that exists, and that every in-page or
cross-page ``#anchor`` points at an id that actually exists in the target page.
It also validates the page list baked into assets/nav.js (links written relative
to the docs root). External links (http/https/mailto) are not fetched.

Exit code is non-zero if anything is missing, so CI fails loudly rather than
shipping a dead link.

Usage:  python3 .github/scripts/check-docs-links.py [docs_dir]
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path


class PageParser(HTMLParser):
    """Collect element ids and link/asset references from one HTML page."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.refs: list[str] = []  # href/src values worth resolving

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        for key in ("href", "src"):
            val = a.get(key)
            if val:
                self.refs.append(val)


def is_external(ref: str) -> bool:
    return ref.startswith(("http://", "https://", "mailto:", "tel:", "data:", "//"))


def parse_page(path: Path) -> PageParser:
    p = PageParser()
    p.feed(path.read_text(encoding="utf-8"))
    return p


def nav_hrefs(nav_js: Path) -> list[str]:
    """The docs-root-relative hrefs listed in assets/nav.js (PAGES entries)."""
    text = nav_js.read_text(encoding="utf-8")
    return re.findall(r'href:\s*"([^"]+)"', text)


def main(argv: list[str]) -> int:
    docs = Path(argv[1] if len(argv) > 1 else "docs").resolve()
    if not docs.is_dir():
        print(f"error: docs directory not found: {docs}", file=sys.stderr)
        return 2

    html_files = sorted(docs.rglob("*.html"))
    # Pre-parse every page so cross-page anchor checks can see target ids.
    parsed = {f: parse_page(f) for f in html_files}
    errors: list[str] = []

    def check_target(source: Path, ref: str) -> None:
        """Resolve one href/src from ``source`` and record any problem."""
        if not ref.strip():
            return
        rel = source.parent
        if ref.startswith("#"):  # in-page anchor
            anchor = ref[1:]
            if anchor and anchor not in parsed[source].ids:
                errors.append(f"{source.relative_to(docs)}: missing in-page anchor #{anchor}")
            return

        file_part, _, anchor = ref.partition("#")
        target = (rel / file_part).resolve()
        if not target.exists():
            errors.append(f"{source.relative_to(docs)}: missing target '{ref}' -> {target.relative_to(docs) if docs in target.parents else target}")
            return
        # If it points at a local HTML page with an anchor, verify the anchor.
        if anchor and target.suffix == ".html" and target in parsed:
            if anchor not in parsed[target].ids:
                errors.append(
                    f"{source.relative_to(docs)}: '{ref}' -> "
                    f"{target.relative_to(docs)} has no id '{anchor}'"
                )

    for f, page in parsed.items():
        for ref in page.refs:
            if is_external(ref):
                continue
            check_target(f, ref)

    # Validate the nav.js page list (hrefs are relative to the docs root).
    nav_js = docs / "assets" / "nav.js"
    if nav_js.exists():
        for href in nav_hrefs(nav_js):
            file_part = href.split("#", 1)[0]
            target = (docs / file_part).resolve()
            if not target.exists():
                errors.append(f"assets/nav.js: page list references missing '{href}'")
    else:
        errors.append("assets/nav.js not found")

    checked = sum(len(p.refs) for p in parsed.values())
    if errors:
        print(f"✗ {len(errors)} broken link(s) across {len(html_files)} page(s):\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"✓ docs link check passed — {len(html_files)} pages, {checked} references, no broken links.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
