"""Fetch a page without letting a hostile URL reach the machine's own network.

A tool that fetches user-supplied URLs is an SSRF primitive unless it checks
where each request really goes. Checking the host name is not enough: a name can
resolve to a private address, redirect to one, or change its answer between the
check and the connection (DNS rebinding). So every hop is resolved once, every
address must be globally routable, and the socket is opened to the vetted IP
itself while TLS still validates the original host name.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

USER_AGENT = "aeo-audit/0.1 (+https://github.com/Nadimul96/aeo-audit)"
_REDIRECTS = frozenset({301, 302, 303, 307, 308})

Resolver = Callable[[str, int], list[str]]


class FetchError(Exception):
    """The page could not be fetched, with a message safe to show to a user."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True, slots=True)
class Response:
    url: str
    status: int
    content_type: str
    body: bytes
    truncated: bool
    redirects: tuple[str, ...]

    def text(self) -> str:
        charset = "utf-8"
        for part in self.content_type.split(";")[1:]:
            key, _, value = part.strip().partition("=")
            if key.lower() == "charset" and value:
                charset = value.strip("\"' ")
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


def system_resolver(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise FetchError(f"Could not resolve {host}.") from error
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def is_public(address: str) -> bool:
    """True only for globally routable addresses (not private, loopback, link-local, etc.)."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


class _Pinned(http.client.HTTPConnection):
    """Connects to a pre-vetted IP address instead of resolving the host again."""

    def __init__(self, host: str, port: int, ip: str, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedTLS(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, ip: str, timeout: float) -> None:
        self._tls = ssl.create_default_context()
        super().__init__(host, port, timeout=timeout, context=self._tls)
        self._ip = ip

    def connect(self) -> None:
        raw = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._tls.wrap_socket(raw, server_hostname=self.host)


def fetch(
    url: str,
    *,
    timeout: float = 10.0,
    max_bytes: int = 2_000_000,
    max_redirects: int = 5,
    allow_private: bool = False,
    resolver: Resolver = system_resolver,
) -> Response:
    """GET `url`, following redirects, checking every hop. Raises `FetchError`."""
    hops: list[str] = []
    current = url.strip()
    for _ in range(max_redirects + 1):
        response = _fetch_once(current, timeout, max_bytes, allow_private, resolver)
        if response.status in _REDIRECTS:
            location = response.location
            if not location:
                raise FetchError(f"HTTP {response.status} without a Location header.")
            hops.append(current)
            current = urljoin(current, location)
            continue
        if response.status >= 400:
            raise FetchError(f"The site returned HTTP {response.status}.", status=response.status)
        return Response(
            current,
            response.status,
            response.content_type,
            response.body,
            response.truncated,
            tuple(hops),
        )
    raise FetchError(f"More than {max_redirects} redirects.")


@dataclass(frozen=True, slots=True)
class _Hop:
    status: int
    location: str
    content_type: str
    body: bytes
    truncated: bool


def _fetch_once(
    url: str, timeout: float, max_bytes: int, allow_private: bool, resolver: Resolver
) -> _Hop:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("Only absolute http and https URLs can be audited.")
    if parts.username or parts.password:
        raise FetchError("URLs with embedded credentials are not accepted.")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as error:
        raise FetchError("The URL has an invalid port.") from error
    addresses = resolver(parts.hostname, port)
    if not addresses:
        raise FetchError(f"Could not resolve {parts.hostname}.")
    if not allow_private and not all(is_public(a) for a in addresses):
        raise FetchError(
            f"{parts.hostname} resolves to a non-public address; "
            "pass allow_private / --allow-private to audit a local site."
        )
    connection = _connect(parts.scheme, parts.hostname, port, addresses, timeout)
    target = parts.path or "/"
    if parts.query:
        target += f"?{parts.query}"
    try:
        connection.request(
            "GET",
            target,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.5",
                "Accept-Encoding": "identity",
            },
        )
        reply = connection.getresponse()
        body = _read_limited(reply, max_bytes + 1, time.monotonic() + timeout * 3)
        return _Hop(
            reply.status,
            reply.getheader("Location") or "",
            reply.getheader("Content-Type") or "",
            body[:max_bytes],
            len(body) > max_bytes,
        )
    except (OSError, http.client.HTTPException) as error:
        raise FetchError(
            f"Could not fetch {parts.hostname}: {error.__class__.__name__}."
        ) from error
    finally:
        connection.close()


def _connect(
    scheme: str, host: str, port: int, addresses: list[str], timeout: float
) -> http.client.HTTPConnection:
    """Open a connection to the first vetted address that accepts one."""
    connection_type = _PinnedTLS if scheme == "https" else _Pinned
    failure: OSError | None = None
    for address in addresses:
        connection = connection_type(host, port, address, timeout)
        try:
            connection.connect()
        except OSError as error:
            failure = error
            connection.close()
            continue
        return connection
    name = failure.__class__.__name__ if failure else "no address"
    raise FetchError(f"Could not fetch {host}: {name}.") from failure


def _read_limited(reply: http.client.HTTPResponse, limit: int, deadline: float) -> bytes:
    """Read at most `limit` bytes, giving up if a slow sender runs past `deadline`."""
    chunks: list[bytes] = []
    total = 0
    while total < limit:
        if time.monotonic() > deadline:
            raise FetchError("The site was too slow to respond.")
        chunk = reply.read(min(65_536, limit - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)
