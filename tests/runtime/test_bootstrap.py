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

ServeBody = Callable[[bytes, str], str]
Answer = tuple[int, Any]
Routes = Mapping[tuple[str, str], Answer]
ServeRoutes = Callable[[Routes], str]

LEAD_IDS = [f"LEAD-00000042-{i:03d}" for i in range(10)]
NOT_FOUND: Answer = (404, {"detail": "not found"})


@pytest.fixture
def serve_body() -> Iterator[ServeBody]:
    """Start a server answering 200 with a fixed body on every path; return its base URL."""
    servers: list[ThreadingHTTPServer] = []

    def serve(body: bytes, content_type: str) -> str:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_POST = do_GET

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


def test_non_json_answer_is_an_invalid_environment(
    serve_body: ServeBody, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEADGEN_URL", serve_body(b"<html>not leadgen</html>", "text/html"))
    monkeypatch.setenv("MAILBOX_URL", serve_body(b"{}", "application/json"))
    with pytest.raises(EnvironmentInvalid, match="leadgen"):
        bootstrap.run()


def test_json_of_the_wrong_shape_is_an_invalid_environment(
    serve_body: ServeBody, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEADGEN_URL", serve_body(b"{}", "application/json"))
    monkeypatch.setenv("MAILBOX_URL", serve_body(b"{}", "application/json"))
    with pytest.raises(EnvironmentInvalid, match="leadgen"):
        bootstrap.run()


def test_malformed_url_is_an_invalid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # httpx2.Client(base_url="http://:abc") raises httpx2.InvalidURL at construction.
    monkeypatch.setenv("LEADGEN_URL", "http://:abc")
    with pytest.raises(EnvironmentInvalid, match="leadgen"):
        bootstrap.run()


def test_unset_database_path_is_a_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UWH_DB")
    with pytest.raises(ValueError, match="UWH_DB"):
        bootstrap.run()


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


def test_lead_that_cannot_be_fetched_is_an_invalid_environment(
    serve_routes: ServeRoutes, monkeypatch: pytest.MonkeyPatch
) -> None:
    leadgen = leadgen_routes(**{f"GET /leads/{LEAD_IDS[3]}": NOT_FOUND})
    with pytest.raises(EnvironmentInvalid, match=f"leadgen lead {LEAD_IDS[3]} failed"):
        bootstrap_against(serve_routes, monkeypatch, leadgen)


def test_envelope_of_another_lead_is_an_invalid_environment(
    serve_routes: ServeRoutes, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = (200, {"lead_id": LEAD_IDS[0], "fields": {}})
    leadgen = leadgen_routes(**{f"GET /leads/{LEAD_IDS[1]}": wrong})
    with pytest.raises(EnvironmentInvalid, match="returned envelope"):
        bootstrap_against(serve_routes, monkeypatch, leadgen)


def test_envelope_without_a_fields_mapping_is_an_invalid_environment(
    serve_routes: ServeRoutes, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = (200, {"lead_id": LEAD_IDS[2], "fields": ["not", "a", "mapping"]})
    leadgen = leadgen_routes(**{f"GET /leads/{LEAD_IDS[2]}": wrong})
    with pytest.raises(EnvironmentInvalid, match="no fields mapping"):
        bootstrap_against(serve_routes, monkeypatch, leadgen)


def test_probe_not_stored_once_is_an_invalid_environment(
    serve_routes: ServeRoutes, monkeypatch: pytest.MonkeyPatch
) -> None:
    mailbox = mailbox_routes(stored=(200, []))
    with pytest.raises(EnvironmentInvalid, match="0 probe messages, not 1"):
        bootstrap_against(serve_routes, monkeypatch, leadgen_routes(), mailbox)


def test_probe_stored_with_other_metadata_is_an_invalid_environment(
    serve_routes: ServeRoutes, monkeypatch: pytest.MonkeyPatch
) -> None:
    mailbox = mailbox_routes(stored=(200, [{"metadata": {"probe": False}}]))
    with pytest.raises(EnvironmentInvalid, match="probe metadata .* differs from sent"):
        bootstrap_against(serve_routes, monkeypatch, leadgen_routes(), mailbox)
