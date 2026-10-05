# ABOUTME: Tests POST /api/commands (A.11): the actor is the underwriter, bound by the REST transport; the response is the A.11 response.
# ABOUTME: Each test runs the app in process against Stand's leadgen and mailbox apps and reads the event log of the application database back.
from fastapi.testclient import TestClient

from tests.api.helpers import first_pass_complete, wait_for
from uwh.api.views import CommandResponse
from uwh.runtime.event_types import EventType
from uwh.runtime.events import read_events
from uwh.runtime.store import open_store
from uwh.settings import Settings


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
    wait_for(lambda: first_pass_complete(client))
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
