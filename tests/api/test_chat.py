# ABOUTME: Tests the chat routes (A.5, A.11): a directive becomes an open card, applying a card submits its command as the underwriter and marks it applied, a dismissed card is closed, and a directive to approve, reject or send is refused with no card.
# ABOUTME: Each test runs the app in process; the model's reply to each message is a recording written under tmp_path for the key the turn will look up, since the tests are of what the app does with a step.
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from uwh.chat.skill import forced_call
from uwh.runtime.event_types import EventType
from uwh.runtime.events import read_events
from uwh.runtime.recordings import Exchange, write_recording
from uwh.runtime.store import open_store
from uwh.settings import Settings


@pytest.fixture
def settings(settings: Settings, tmp_path: Path) -> Settings:
    return replace(settings, recordings_dir=str(tmp_path / "recordings"))


@pytest.fixture
def lead(client: TestClient) -> Iterator[str]:
    client.post("/api/run/start?wait=true")
    db = open_store(client.app.state.runtime.settings.db_path)  # type: ignore[attr-defined]
    (lead_id,) = db.execute("SELECT lead_id FROM leads ORDER BY rowid LIMIT 1").fetchone()
    db.close()
    yield str(lead_id)


def reply_with(settings: Settings, message: str, lead_id: str, tool_input: dict[str, Any]) -> None:
    """Record what the model returns for the first call of a turn on `message`."""
    call = forced_call({"message": message, "lead_id": lead_id, "steps": []})
    key = call.recording_key
    write_recording(
        Path(settings.recordings_dir),
        key,
        Exchange(
            skill=key.skill,
            prompt_version=key.prompt_version,
            input_hash=key.input_hash,
            input=dict(call.shown),
            model_id="deepseek-flash",
            request_id="",
            stop_reason="tool_use",
            tokens_in=1,
            tokens_out=1,
            tool_input=tool_input,
        ),
    )


def propose(command_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": "propose_command",
        "command_type": command_type,
        "command_payload": payload,
        "rationale": "Because the underwriter asked.",
    }


def chat(client: TestClient, message: str, lead_id: str) -> dict[str, Any]:
    response = client.post("/api/chat", json={"lead_id": lead_id, "message": message})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def events(settings: Settings, event_type: EventType) -> list[Any]:
    db = open_store(settings.db_path)
    try:
        return [e for e in read_events(db) if e.type == event_type]
    finally:
        db.close()


def test_a_directive_becomes_an_open_card_that_changes_nothing(
    client: TestClient, settings: Settings, lead: str
) -> None:
    reply_with(
        settings, "Decline it", lead, propose("decline_lead", {"lead_id": lead, "reason": "x"})
    )

    answer = chat(client, "Decline it", lead)

    card = answer["proposal"]
    assert card["payload"]["type"] == "decline_lead"
    assert client.get("/api/proposals").json() == [card]
    assert events(settings, EventType.ruling_recorded) == []


def test_applying_a_card_submits_its_command_as_the_underwriter_and_closes_it(
    client: TestClient, settings: Settings, lead: str
) -> None:
    reply_with(
        settings, "Decline it", lead, propose("decline_lead", {"lead_id": lead, "reason": "x"})
    )
    card = chat(client, "Decline it", lead)["proposal"]

    applied = client.post(f"/api/proposals/{card['proposal_id']}/apply")

    assert applied.json()["accepted"] is True
    (ruling,) = events(settings, EventType.ruling_recorded)
    assert ruling.actor == "underwriter" and ruling.id == applied.json()["event_id"]
    assert client.get("/api/proposals").json() == []
    assert client.post(f"/api/proposals/{card['proposal_id']}/apply").status_code == 409


def test_a_card_whose_command_is_refused_stays_open(
    client: TestClient, settings: Settings, lead: str
) -> None:
    reply_with(
        settings, "Decline L-X", lead, propose("decline_lead", {"lead_id": "L-X", "reason": "x"})
    )
    card = chat(client, "Decline L-X", lead)["proposal"]

    applied = client.post(f"/api/proposals/{card['proposal_id']}/apply").json()

    assert applied["accepted"] is False and "L-X" in applied["reason"]
    assert [c["proposal_id"] for c in client.get("/api/proposals").json()] == [card["proposal_id"]]


def test_a_dismissed_card_is_closed_and_runs_nothing(
    client: TestClient, settings: Settings, lead: str
) -> None:
    reply_with(
        settings, "Decline it", lead, propose("decline_lead", {"lead_id": lead, "reason": "x"})
    )
    card = chat(client, "Decline it", lead)["proposal"]

    dismissed = client.post(f"/api/proposals/{card['proposal_id']}/dismiss")

    assert dismissed.status_code == 200
    assert client.get("/api/proposals").json() == []
    assert events(settings, EventType.ruling_recorded) == []
    assert client.post(f"/api/proposals/{card['proposal_id']}/dismiss").status_code == 409
    assert client.post("/api/proposals/999/dismiss").status_code == 404


@pytest.mark.parametrize("message", ["Approve the draft", "Please go ahead and approve it"])
def test_a_directive_to_approve_is_refused_as_the_assistant_and_leaves_no_card(
    client: TestClient, settings: Settings, lead: str, message: str
) -> None:
    reply_with(settings, message, lead, propose("approve", {"item_id": 1, "reason": "ok"}))

    answer = chat(client, message, lead)

    assert answer["proposal"] is None and "nothing is waiting" in answer["answer"]
    assert "approve" not in answer["answer"]
    (refusal,) = [e for e in events(settings, EventType.command_refused) if e.actor == "assistant"]
    assert refusal.payload.command_type == "propose_command"
    assert client.get("/api/proposals").json() == []


def test_a_turn_with_no_recording_answers_409_and_records_the_miss(
    client: TestClient, settings: Settings, lead: str
) -> None:
    response = client.post("/api/chat", json={"lead_id": lead, "message": "unrecorded"})

    assert response.status_code == 409
    assert len(events(settings, EventType.replay_miss)) == 1


def test_an_empty_message_is_not_a_turn(client: TestClient) -> None:
    assert client.post("/api/chat", json={"message": ""}).status_code == 422


def test_the_proposals_table_is_the_cards_store(
    client: TestClient, settings: Settings, lead: str
) -> None:
    reply_with(
        settings, "Decline it", lead, propose("decline_lead", {"lead_id": lead, "reason": "x"})
    )
    chat(client, "Decline it", lead)

    db = sqlite3.connect(settings.db_path)
    assert db.execute("SELECT state, actor FROM proposals").fetchall() == [("open", "assistant")]
    db.close()
