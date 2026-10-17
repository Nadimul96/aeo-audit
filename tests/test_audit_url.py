"""audit_url end to end against a local server, with no external network."""

from __future__ import annotations

import pytest

from aeo_audit import FetchError, audit_url
from conftest import fixture_text
from support_server import Site, serve


def test_a_page_and_its_robots_txt_are_fetched_and_audited() -> None:
    site = Site()
    with serve(site):
        site.add("/guides/x", fixture_text("well-structured.html"))
        site.add("/robots.txt", fixture_text("robots-blocking.txt"), content_type="text/plain")
        audit = audit_url(f"http://127.0.0.1:{site.port}/guides/x", allow_private=True)
    assert audit.grade in ("A", "B")
    assert set(audit.blocked_agents) == {"OAI-SearchBot", "PerplexityBot", "GPTBot"}


def test_a_missing_robots_txt_means_nothing_is_blocked() -> None:
    site = Site()
    with serve(site):
        site.add("/guide", "<h1>x</h1><p>text</p>")
        audit = audit_url(f"http://127.0.0.1:{site.port}/guide", allow_private=True)
    assert audit.blocked_agents == ()
    assert audit.signals[0].score == 100


def test_a_failing_robots_txt_is_reported_and_scored_low() -> None:
    site = Site()
    with serve(site):
        site.add("/guide", "<h1>x</h1><p>text</p>")
        site.add("/robots.txt", status=503, body="busy")
        audit = audit_url(f"http://127.0.0.1:{site.port}/guide", allow_private=True)
    assert audit.signals[0].score == 20
    assert any("robots.txt could not be read" in note for note in audit.notes)


def test_redirects_and_truncation_are_noted() -> None:
    site = Site()
    with serve(site):
        site.add("/old", status=301, headers={"Location": "/new"})
        site.add("/new", "<p>" + "word " * 600_000 + "</p>")
        audit = audit_url(f"http://127.0.0.1:{site.port}/old", allow_private=True)
    assert audit.url.endswith("/new")
    assert any("redirect" in note for note in audit.notes)
    assert any("cut off" in note for note in audit.notes)


def test_non_html_responses_are_refused() -> None:
    site = Site()
    with serve(site):
        site.add("/data", b'{"a": 1}', content_type="application/json")
        with pytest.raises(FetchError, match="Expected an HTML page"):
            audit_url(f"http://127.0.0.1:{site.port}/data", allow_private=True)


def test_local_addresses_are_refused_by_default() -> None:
    with pytest.raises(FetchError, match="non-public"):
        audit_url("http://127.0.0.1:1/")


def test_a_bare_host_gets_https() -> None:
    with pytest.raises(FetchError, match="non-public"):
        audit_url("localhost/")
