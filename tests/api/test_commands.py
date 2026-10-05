# ABOUTME: Tests POST /api/commands (A.11): the actor is the underwriter, bound by the REST transport; the response is the A.11 response; workflow-only classes are not accepted; a command whose handler is not built answers 501.
# ABOUTME: Each test runs the app in process against Stand's leadgen and mailbox apps and reads the event log of the application database back.
import time

import pytest
from fastapi.testclient import TestClient

from uwh.api.views import CommandResponse
from uwh.runtime.event_types import EventType
from uwh.runtime.events import read_events
from uwh.runtime.store import open_store
from uwh.settings import Settings
from uwh.skills.vertical import COMMAND_CLASSES

WORKFLOW_ONLY = [c.name for c in COMMAND_CLASSES if c.actors == ("workflow",)]


def post(client: TestClient, command_type: str, payload: dict[str, object]) -> CommandResponse:
    response = client.post("/api/commands", json={"type": command_type, "payload": payload})
    assert response.status_code == 200
    return CommandResponse.model_validate(response.json())


def test_a_start_run_command_is_accepted_and_its_pass_settles_the_run(
    client: TestClient, settings: Settings
) -> None:
    response = post(client, "start_run", {"seed": 11})

    assert response.accepted is True
    assert response.reason is None
    assert response.event_id is not None
    deadline = time.monotonic() + 10
    while not client.get("/api/run").json()["first_pass_complete"]:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    db = open_store(settings.db_path)
    (started,) = [e for e in read_events(db) if e.type is EventType.run_started]
    assert (started.id, started.actor) == (response.event_id, "underwriter")
    assert db.execute("SELECT seed FROM runs").fetchone() == (11,)
    db.close()


def test_the_actor_of_a_command_is_the_underwriter_the_transport_binds(
    client: TestClient, settings: Settings
) -> None:
    response = post(client, "reject", {"item_id": 99, "reason": "no such item"})

    assert response.accepted is False
    assert response.reason is not None and "99" in response.reason
    db = open_store(settings.db_path)
    (refused,) = [e for e in read_events(db) if e.type is EventType.command_refused]
    assert (refused.id, refused.actor, refused.run_id) == (
        response.event_id,
        "underwriter",
        "pre-run",
    )
    db.close()


def test_an_accepted_command_returns_the_event_it_produced(client: TestClient) -> None:
    client.post("/api/run/start?wait=true")
    db = open_store(client.app.state.runtime.settings.db_path)  # type: ignore[attr-defined]
    (lead_id,) = db.execute("SELECT lead_id FROM leads ORDER BY rowid LIMIT 1").fetchone()
    db.close()

    response = post(
        client,
        "resolve_fact",
        {"lead_id": lead_id, "key": "acreage", "value": 3, "reason": "the producer called"},
    )

    assert response.accepted is True
    assert response.event_id is not None


def test_a_payload_that_names_an_actor_is_not_accepted(client: TestClient) -> None:
    response = client.post(
        "/api/commands",
        json={
            "type": "reject",
            "payload": {"item_id": 1, "reason": "x", "actor": "workflow"},
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize("command_type", WORKFLOW_ONLY)
def test_a_workflow_only_class_is_not_accepted_over_http(
    client: TestClient, command_type: str
) -> None:
    response = client.post("/api/commands", json={"type": command_type, "payload": {}})

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["type"] == "union_tag_invalid"
    assert (error["ctx"]["discriminator"], error["ctx"]["tag"]) == ("'type'", command_type)


def test_a_command_whose_handler_is_not_built_answers_501(client: TestClient) -> None:
    response = client.post(
        "/api/commands",
        json={"type": "decline_lead", "payload": {"lead_id": "L-1", "reason": "out of appetite"}},
    )

    assert response.status_code == 501
    assert "not built" in response.json()["detail"]
