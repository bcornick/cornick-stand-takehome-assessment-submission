# ABOUTME: Fast tests that the bootstrap turns a wrong service at the configured URL into EnvironmentInvalid.
# ABOUTME: Real local HTTP servers stand in for a wrong service, the same idea as a closed port; no containers.
import json
import threading
from collections.abc import Callable, Iterator, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from uwh.runtime import bootstrap
from uwh.runtime.bootstrap import EnvironmentInvalid

Answer = tuple[int, Any]
Routes = Mapping[tuple[str, str], Answer]
ServeRoutes = Callable[[Routes], str]

LEAD_IDS = [f"LEAD-00000042-{i:03d}" for i in range(10)]
NOT_FOUND: Answer = (404, {"detail": "not found"})


@pytest.fixture
def serve_routes() -> Iterator[ServeRoutes]:
    """Start a server answering JSON per (method, path); return its base URL.

    A path key ending in `*` matches every path with that prefix. Unlisted paths answer 404.
    """
    servers: list[ThreadingHTTPServer] = []

    def serve(routes: Routes) -> str:
        class Handler(BaseHTTPRequestHandler):
            def answer(self) -> None:
                path = urlsplit(self.path).path
                status, payload = routes.get((self.command, path), NOT_FOUND)
                if (self.command, path) not in routes:
                    for (method, pattern), candidate in routes.items():
                        if (
                            method == self.command
                            and pattern.endswith("*")
                            and path.startswith(pattern[:-1])
                        ):
                            status, payload = candidate
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = answer
            do_POST = answer

            def log_message(self, format: str, *args: object) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        ).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield serve
    for server in servers:
        server.shutdown()
        server.server_close()


def leadgen_routes(**changes: Answer) -> dict[tuple[str, str], Answer]:
    """Answers Stand's leadgen would give for the ten seeded leads; `changes` maps "METHOD path" to a replacement."""
    routes: dict[tuple[str, str], Answer] = {
        ("GET", "/healthz"): (200, {"status": "ok"}),
        ("POST", "/queue"): (200, {"lead_ids": LEAD_IDS}),
        ("GET", "/leads"): (200, [{"lead_id": lead_id} for lead_id in LEAD_IDS]),
    }
    for lead_id in LEAD_IDS:
        routes[("GET", f"/leads/{lead_id}")] = (200, {"lead_id": lead_id, "fields": {}})
    for key, answer in changes.items():
        method, path = key.split(" ", 1)
        routes[(method, path)] = answer
    return routes


def mailbox_routes(stored: Answer) -> dict[tuple[str, str], Answer]:
    """Mailbox answers that accept the probe send; `stored` is the answer for the probe read."""
    return {
        ("GET", "/healthz"): (200, {"status": "ok"}),
        ("POST", "/emails"): (200, {"id": 1}),
        ("GET", "/leads/BOOTSTRAP-*"): stored,
    }


@pytest.fixture(autouse=True)
def database_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UWH_DB", str(tmp_path / "app.db"))


def bootstrap_against(
    serve_routes: ServeRoutes,
    monkeypatch: pytest.MonkeyPatch,
    leadgen: Routes,
    mailbox: Routes | None = None,
) -> None:
    monkeypatch.setenv("LEADGEN_URL", serve_routes(leadgen))
    monkeypatch.setenv(
        "MAILBOX_URL", serve_routes(mailbox or {("GET", "/healthz"): (200, {"status": "ok"})})
    )
    bootstrap.run()


def test_lead_list_differing_from_the_queue_is_an_invalid_environment(
    serve_routes: ServeRoutes, monkeypatch: pytest.MonkeyPatch
) -> None:
    reversed_list = [{"lead_id": lead_id} for lead_id in reversed(LEAD_IDS)]
    leadgen = leadgen_routes(**{"GET /leads": (200, reversed_list)})
    with pytest.raises(EnvironmentInvalid, match="lead list .* differs from the queue"):
        bootstrap_against(serve_routes, monkeypatch, leadgen)


def test_probe_not_stored_once_is_an_invalid_environment(
    serve_routes: ServeRoutes, monkeypatch: pytest.MonkeyPatch
) -> None:
    mailbox = mailbox_routes(stored=(200, []))
    with pytest.raises(EnvironmentInvalid, match="0 probe messages, not 1"):
        bootstrap_against(serve_routes, monkeypatch, leadgen_routes(), mailbox)
