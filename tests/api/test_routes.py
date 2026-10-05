# ABOUTME: Tests that the app's OpenAPI paths are the A.5 route table and that every route except GET /api/run is declared and answers 501.
# ABOUTME: The expected paths and methods are written out from A.5; /mcp is mounted outside OpenAPI and is not among them.
from typing import Any

import pytest
from fastapi.testclient import TestClient

from uwh.api.app import create_app
from uwh.settings import Settings

# A.5, one entry per path, in A.5's spelling of the path parameter.
A5_ROUTES = {
    "/api/run": {"get"},
    "/api/run/start": {"post"},
    "/api/leads": {"get"},
    "/api/leads/{id}": {"get"},
    "/api/leads/{id}/events": {"get"},
    "/api/items": {"get"},
    "/api/commands": {"post"},
    "/api/replies": {"post"},
    "/api/replies/fixtures": {"post"},
    "/api/settings": {"get"},
    "/api/skills": {"get"},
    "/api/proposals": {"get"},
    "/api/chat": {"post"},
    "/api/events/stream": {"get"},
}

LEAD = "LEAD-00000042-000"
REPLY = {"lead_id": LEAD, "intent_id": "intent-1", "body": "The roof is slate."}

# One valid request for every route that is not yet built.
NOT_BUILT = [
    ("post", "/api/run/start", None),
    ("post", "/api/run/start?wait=true", None),
    ("get", "/api/leads", None),
    ("get", f"/api/leads/{LEAD}", None),
    ("get", f"/api/leads/{LEAD}/events", None),
    ("get", "/api/items", None),
    (
        "post",
        "/api/commands",
        {"type": "reject", "payload": {"item_id": 1, "reason": "wrong recipient"}},
    ),
    ("post", "/api/replies", REPLY),
    ("post", "/api/replies/fixtures", None),
    ("get", "/api/settings", None),
    ("get", "/api/skills", None),
    ("get", "/api/proposals", None),
    ("post", "/api/chat", {"message": "why is lead 003 held?"}),
    ("get", "/api/events/stream", None),
]


@pytest.fixture
def app_client() -> TestClient:
    return TestClient(create_app(Settings.load({"UWH_DB": "unused.db"})))


def document() -> dict[str, Any]:
    return create_app(Settings.load({"UWH_DB": "unused.db"})).openapi()


def test_openapi_paths_are_the_a5_table() -> None:
    paths = document()["paths"]
    assert set(paths) == set(A5_ROUTES)
    assert len(paths) == 14
    for path, methods in A5_ROUTES.items():
        assert set(paths[path]) == methods, path


def test_mcp_is_not_in_the_openapi_document() -> None:
    assert "/mcp" not in document()["paths"]


@pytest.mark.parametrize(("method", "url", "body"), NOT_BUILT)
def test_unbuilt_route_answers_501_with_a_json_detail(
    app_client: TestClient, method: str, url: str, body: dict[str, Any] | None
) -> None:
    response = app_client.request(method, url, json=body)
    assert response.status_code == 501
    assert response.headers["content-type"] == "application/json"
    assert "not implemented" in response.json()["detail"]


def test_every_a5_route_but_run_is_covered_by_the_501_cases() -> None:
    covered = {url.split("?")[0] for _, url, _ in NOT_BUILT}
    covered = {u.replace(LEAD, "{id}") for u in covered}
    assert covered == set(A5_ROUTES) - {"/api/run"}


def test_run_start_declares_the_wait_flag() -> None:
    parameters = document()["paths"]["/api/run/start"]["post"]["parameters"]
    wait = next(p for p in parameters if p["name"] == "wait")
    assert wait["in"] == "query"
    assert wait["schema"]["type"] == "boolean"


def test_event_stream_declares_server_sent_events_and_last_event_id() -> None:
    operation = document()["paths"]["/api/events/stream"]["get"]
    assert "text/event-stream" in operation["responses"]["200"]["content"]
    header = next(p for p in operation["parameters"] if p["in"] == "header")
    assert header["name"].lower() == "last-event-id"


def test_a_reply_body_over_8000_characters_is_refused(app_client: TestClient) -> None:
    response = app_client.post("/api/replies", json={**REPLY, "body": "x" * 8001})
    assert response.status_code == 422
    assert app_client.post("/api/replies", json={**REPLY, "body": "x" * 8000}).status_code == 501


def test_a_command_the_http_surface_does_not_accept_is_refused(app_client: TestClient) -> None:
    response = app_client.post("/api/commands", json={"type": "fetch_data", "payload": {}})
    assert response.status_code == 422
