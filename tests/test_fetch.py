"""The fetcher must never be talked into reaching the local network."""

from __future__ import annotations

import pytest

from aeo_audit import fetch as fetch_module
from aeo_audit.fetch import FetchError, fetch, is_public
from support_server import Site, serve


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "127.8.8.8",
        "10.0.0.1",
        "172.16.5.4",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "240.0.0.1",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "fe80::1%eth0",
        "not-an-ip",
        "",
    ],
)
def test_non_public_and_malformed_addresses_are_rejected(address: str) -> None:
    assert not is_public(address)


@pytest.mark.parametrize("address", ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111"])
def test_public_addresses_are_accepted(address: str) -> None:
    assert is_public(address)


def test_a_host_resolving_to_a_private_address_is_refused_before_any_connection() -> None:
    with pytest.raises(FetchError, match="non-public"):
        fetch("http://innocent.test/", resolver=lambda _h, _p: ["10.0.0.5"])


def test_one_private_address_among_public_ones_is_enough_to_refuse() -> None:
    with pytest.raises(FetchError, match="non-public"):
        fetch("http://mixed.test/", resolver=lambda _h, _p: ["8.8.8.8", "169.254.169.254"])


@pytest.mark.parametrize(
    "url",
    [
        "ftp://site.example/",
        "file:///etc/passwd",
        "http://user:pw@site.example/",
        "http://",
        "x",
        "http://site.example:99999/",
    ],
)
def test_unsupported_urls_are_refused(url: str) -> None:
    with pytest.raises(FetchError):
        fetch(url, resolver=lambda _h, _p: ["8.8.8.8"])


def test_a_redirect_to_a_private_address_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    site = Site()
    names = {"first.test": "127.0.0.1", "second.test": "10.0.0.9"}
    monkeypatch.setattr(fetch_module, "is_public", lambda address: address == "127.0.0.1")
    with serve(site):
        site.add("/", status=302, headers={"Location": f"http://second.test:{site.port}/x"})
        with pytest.raises(FetchError, match=r"second\.test resolves to a non-public"):
            fetch(f"http://first.test:{site.port}/", resolver=lambda h, _p: [names[h]])


def test_the_socket_goes_to_the_vetted_ip_while_the_host_header_keeps_the_name() -> None:
    site, calls = Site(), []

    def resolver(host: str, _port: int) -> list[str]:
        calls.append(host)
        return ["127.0.0.1"]

    with serve(site):
        site.add("/", "<p>hi</p>")
        response = fetch(f"http://pinned.test:{site.port}/", allow_private=True, resolver=resolver)
    assert response.text() == "<p>hi</p>"
    assert site.seen_hosts == [f"pinned.test:{site.port}"]
    assert calls == ["pinned.test"], "the host must be resolved once per hop, not again at connect"


def test_redirects_are_followed_and_recorded() -> None:
    site = Site()
    with serve(site):
        site.add("/a", status=301, headers={"Location": "/b"})
        site.add("/b", status=302, headers={"Location": f"http://localhost:{site.port}/c"})
        site.add("/c", "<p>done</p>")
        response = fetch(f"http://127.0.0.1:{site.port}/a", allow_private=True)
    assert response.url.endswith("/c")
    assert len(response.redirects) == 2


def test_a_redirect_loop_gives_up() -> None:
    site = Site()
    with serve(site):
        site.add("/", status=302, headers={"Location": "/"})
        with pytest.raises(FetchError, match="redirects"):
            fetch(f"http://127.0.0.1:{site.port}/", allow_private=True, max_redirects=3)


def test_http_errors_carry_their_status() -> None:
    site = Site()
    with serve(site):
        with pytest.raises(FetchError) as error:
            fetch(f"http://127.0.0.1:{site.port}/missing", allow_private=True)
    assert error.value.status == 404


def test_large_bodies_are_cut_off_and_flagged() -> None:
    site = Site()
    with serve(site):
        site.add("/big", b"x" * 5000)
        response = fetch(f"http://127.0.0.1:{site.port}/big", allow_private=True, max_bytes=1000)
    assert len(response.body) == 1000
    assert response.truncated


def test_the_declared_charset_is_used_and_bad_ones_are_survivable() -> None:
    site = Site()
    with serve(site):
        site.add("/latin", "café".encode("latin-1"), content_type="text/html; charset=latin-1")
        site.add("/weird", b"ok", content_type="text/html; charset=nonsense")
        base = f"http://127.0.0.1:{site.port}"
        assert fetch(f"{base}/latin", allow_private=True).text() == "café"
        assert fetch(f"{base}/weird", allow_private=True).text() == "ok"


def test_a_server_that_trickles_bytes_is_cut_off() -> None:
    site = Site()
    with serve(site):
        site.add("/slow", b"abcdefghijklmnop")
        site.slow.add("/slow")
        with pytest.raises(FetchError, match=r"too slow|Could not fetch"):
            fetch(f"http://127.0.0.1:{site.port}/slow", allow_private=True, timeout=0.3)


def test_a_closed_port_is_a_clean_error() -> None:
    with pytest.raises(FetchError, match="Could not fetch"):
        fetch("http://127.0.0.1:9/", allow_private=True, timeout=1)
