from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "waf-data.json"


@pytest.fixture(autouse=True)
def _use_fixture_questions(monkeypatch):
    """Point the question loader at the small test fixture, not repo /data."""
    monkeypatch.setenv("WAF_DATA_PATH", str(FIXTURE))
