# ABOUTME: Fast tests that the bootstrap turns a wrong service at the configured URL into EnvironmentInvalid.
# ABOUTME: Real local HTTP servers stand in for a wrong service, the same idea as a closed port; no containers.
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from uwh.runtime import bootstrap
from uwh.runtime.bootstrap import EnvironmentInvalid

ServeBody = Callable[[bytes, str], str]


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
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield serve
    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.fixture(autouse=True)
def database_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UWH_DB", str(tmp_path / "app.db"))


def test_non_json_answer_is_an_invalid_environment(
    serve_body: ServeBody, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEADGEN_URL", serve_body(b"<html>not leadgen</html>", "text/html"))
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
    with pytest.raises(ValueError, match="UWH_DB") as raised:
        bootstrap.run()
    assert not isinstance(raised.value, EnvironmentInvalid)
