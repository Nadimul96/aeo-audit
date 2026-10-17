"""A tiny local HTTP server whose routes each test defines."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

Route = tuple[int, dict[str, str], bytes]


class Site:
    def __init__(self) -> None:
        self.routes: dict[str, Route] = {}
        self.slow: set[str] = set()
        self.seen_hosts: list[str] = []
        self.port = 0

    def add(
        self,
        path: str,
        body: bytes | str = b"",
        *,
        status: int = 200,
        content_type: str = "text/html; charset=utf-8",
        headers: dict[str, str] | None = None,
    ) -> None:
        payload = body.encode() if isinstance(body, str) else body
        self.routes[path] = (status, {"Content-Type": content_type, **(headers or {})}, payload)


def _handler(site: Site) -> Callable[..., BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            site.seen_hosts.append(self.headers.get("Host", ""))
            route = site.routes.get(self.path)
            if route is None:
                self.send_error(404)
                return
            status, headers, body = route
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                if self.path in site.slow:
                    for byte in body:
                        time.sleep(0.4)
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                else:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                return  # the client gave up, which is what the slow-body test wants

        def log_message(self, *_args: object) -> None:
            return

    return Handler


@contextmanager
def serve(site: Site) -> Iterator[Site]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(site))
    site.port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield site
    finally:
        server.shutdown()
        server.server_close()
