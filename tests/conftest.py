from __future__ import annotations

from datetime import UTC, datetime
from importlib.resources import files

import pytest

NOW = datetime(2026, 10, 17, tzinfo=UTC)
GOOD_URL = "https://tidepool-coffee.example/guides/how-long-does-cold-brew-last"
THIN_URL = "https://harborroast.example/"
_FIXTURES = files("aeo_audit") / "fixtures"


def fixture_text(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def good_html() -> str:
    return fixture_text("well-structured.html")


@pytest.fixture
def thin_html() -> str:
    return fixture_text("thin.html")
