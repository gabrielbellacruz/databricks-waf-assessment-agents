"""Copy the canonical question set into the package before building the wheel.

The single source of truth is repo-root /data/waf-data.json. The Job installs
the agent as a wheel, so the file must travel inside the wheel; this copies it
to waf_agents/data/ (git-ignored) where force-include picks it up.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root
SRC = ROOT / "data" / "waf-data.json"
DEST = ROOT / "agents" / "waf_agents" / "data" / "waf-data.json"


def main() -> int:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DEST)
    print(f"copied {SRC} -> {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
