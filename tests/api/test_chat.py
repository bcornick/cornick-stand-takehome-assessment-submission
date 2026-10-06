# ABOUTME: Tests the chat routes (A.5, A.11): a turn answers as a stream that ends with exactly one closing event, a directive becomes an open card on its lead, applying a card submits its command as the underwriter, and a directive the assistant may not propose is refused with no card.
# ABOUTME: Each test runs the app in process in live mode with a scripted model, since the tests are of what the app does with a step; one test runs it in replay.
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import replay_settings
from tests.chat.helpers import Script
from uwh.api import runtime
from uwh.api.app import create_app
from uwh.chat.examples import EXAMPLE_PROMPTS
from uwh.chat.skill import forced_call
from uwh.runtime.event_types import EventType
from uwh.runtime.events import read_events
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.recordings import Exchange, write_recording
from uwh.runtime.store import open_store
from uwh.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return replay_settings(tmp_path, 7, RUN_MODE="live", MODEL_API_KEY="scripted")


@pytest.fixture(autouse=True)
def model(monkeypatch: pytest.MonkeyPatch) -> Script:
    """The model the app calls: each test appends the tool inputs it returns, in order."""
    script = Script()
    monkeypatch.setattr(runtime, "anthropic_call", lambda client, model_id: script)
    return script


@pytest.fixture
def lead(client: TestClient) -> Iterator[str]:
    client.post("/api/run/start?wait=true")
    db = open_store(client.app.state.runtime.settings.db_path)  # type: ignore[attr-defined]
    (lead_id,) = db.execute("SELECT lead_id FROM leads ORDER BY rowid LIMIT 1").fetchone()
    db.close()
    yield str(lead_id)


def propose(command_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": "propose_command",
        "command_type": command_type,
        "command_payload": payload,
        "rationale": "Because the underwriter asked.",
    }


def chat(client: TestClient, message: str, lead_id: str | None) -> list[dict[str, Any]]:
    """The events of the turn's stream, in order."""
    response = client.post("/api/chat", json={"lead_id": lead_id, "message": message})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def proposed(client: TestClient, model: Script, lead: str, target: str) -> int:
    """Have the assistant propose declining `target` from `lead`'s conversation; the card's id."""
    model.tool_inputs.append(propose("decline_lead", {"lead_id": target, "reason": "x"}))
    (closing,) = chat(client, "Decline it", lead)
    assert closing["type"] == "proposal"
    return int(closing["proposal_id"])


def events(settings: Settings, event_type: EventType) -> list[Any]:
    db = open_store(settings.db_path)
    try:
        return [e for e in read_events(db) if e.type == event_type]
    finally:
        db.close()


def test_the_stream_carries_each_lookup_and_ends_with_exactly_one_closing_event(
    client: TestClient, model: Script, lead: str
) -> None:
    model.tool_inputs += [
        {"action": "lead_events", "lead_id": lead},
        {"action": "lead_summary", "lead_id": lead},
        {"action": "answer", "answer": "It arrived today.", "citations": [1, 99]},
    ]

    stream = chat(client, "What happened?", lead)

    assert [event["type"] for event in stream] == ["step", "step", "answer"]
    assert stream[0]["summary"].startswith("Read the events of lead ")
    closing = stream[-1]
    assert closing["answer"] == "It arrived today."
    (citation,) = closing["citations"]
    assert (citation["number"], citation["lead_id"], citation["kind"]) == (1, lead, "event")


def test_replay_answers_that_questions_need_live_mode_and_calls_no_model(
    tmp_path: Path, leadgen: LeadgenClient, mailbox: MailboxClient
) -> None:
    settings = replay_settings(tmp_path, 7)
    with TestClient(create_app(settings, leadgen=leadgen, mailbox=mailbox)) as client:
        stream = chat(client, "What happened?", "L-1")

    assert stream == [{"type": "error", "reason": "Questions need live mode"}]
    assert events(settings, EventType.model_called) == []
    assert events(settings, EventType.replay_miss) == []


def test_replay_answers_an_example_prompt_from_its_recording_and_any_other_turn_needs_live_mode(
    tmp_path: Path, leadgen: LeadgenClient, mailbox: MailboxClient
) -> None:
    example = EXAMPLE_PROMPTS[0]
    settings = replay_settings(tmp_path, 7, UWH_RECORDINGS=str(tmp_path / "recordings"))
    call = forced_call({"message": example, "lead_id": None, "history": [], "steps": []})
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
            tool_input={"action": "answer", "answer": "Nothing is waiting on you."},
        ),
    )
    needs_live = [{"type": "error", "reason": "Questions need live mode"}]
    with TestClient(create_app(settings, leadgen=leadgen, mailbox=mailbox)) as client:
        client.post("/api/run/start?wait=true")
        (closing,) = chat(client, example, None)
        # The same words in a lead's conversation, and an example with no recording, are not answered.
        on_a_lead = chat(client, example, "L-1")
        unrecorded = chat(client, EXAMPLE_PROMPTS[1], None)

    assert closing == {"type": "answer", "answer": "Nothing is waiting on you.", "citations": []}
    assert on_a_lead == needs_live and unrecorded == needs_live


def test_a_turn_with_no_model_key_closes_with_an_error(
    tmp_path: Path, leadgen: LeadgenClient, mailbox: MailboxClient
) -> None:
    settings = replay_settings(tmp_path, 7, RUN_MODE="live")
    with TestClient(create_app(settings, leadgen=leadgen, mailbox=mailbox)) as client:
        (closing,) = chat(client, "What happened?", "L-1")

    assert closing == {"type": "error", "reason": "The assistant has no model key"}


def test_a_turn_that_fails_still_closes_the_stream_with_an_error(
    client: TestClient, lead: str, caplog: pytest.LogCaptureFixture
) -> None:
    # The scripted model has nothing to return, so its call raises inside the turn's thread.
    (closing,) = chat(client, "What happened?", lead)

    assert closing["type"] == "error" and closing["reason"].startswith("The assistant failed")
    assert "the chat turn failed" in caplog.text


def test_a_directive_becomes_an_open_card_on_its_lead_that_changes_nothing(
    client: TestClient, model: Script, settings: Settings, lead: str
) -> None:
    model.tool_inputs.append(propose("decline_lead", {"lead_id": lead, "reason": "x"}))

    stream = chat(client, "Decline it", lead)

    (card,) = client.get("/api/proposals").json()
    assert stream == [{"type": "proposal", "proposal_id": card["proposal_id"], "lead_id": lead}]
    assert card["lead_id"] == lead and card["payload"]["type"] == "decline_lead"
    assert events(settings, EventType.ruling_recorded) == []


def test_a_proposal_lands_on_the_lead_it_targets_not_the_one_it_was_asked_on(
    client: TestClient, model: Script, settings: Settings, lead: str
) -> None:
    db = open_store(settings.db_path)
    (other,) = db.execute("SELECT lead_id FROM leads WHERE lead_id != ?", (lead,)).fetchone()
    db.close()

    proposed(client, model, lead, other)

    (card,) = client.get("/api/proposals").json()
    assert card["lead_id"] == other


def test_applying_a_card_submits_its_command_as_the_underwriter_and_closes_it(
    client: TestClient, model: Script, settings: Settings, lead: str
) -> None:
    card = proposed(client, model, lead, lead)

    applied = client.post(f"/api/proposals/{card}/apply")

    assert applied.json()["accepted"] is True
    (ruling,) = events(settings, EventType.ruling_recorded)
    assert ruling.actor == "underwriter" and ruling.id == applied.json()["event_id"]
    assert client.get("/api/proposals").json() == []
    assert client.post(f"/api/proposals/{card}/apply").status_code == 409


def test_a_card_whose_command_is_refused_stays_open(
    client: TestClient, model: Script, lead: str
) -> None:
    card = proposed(client, model, lead, "L-X")

    applied = client.post(f"/api/proposals/{card}/apply").json()

    assert applied["accepted"] is False and "L-X" in applied["reason"]
    assert [c["proposal_id"] for c in client.get("/api/proposals").json()] == [card]


def test_a_dismissed_card_is_closed_and_runs_nothing(
    client: TestClient, model: Script, settings: Settings, lead: str
) -> None:
    card = proposed(client, model, lead, lead)

    dismissed = client.post(f"/api/proposals/{card}/dismiss")

    assert dismissed.status_code == 200
    assert client.get("/api/proposals").json() == []
    assert events(settings, EventType.ruling_recorded) == []
    assert client.post(f"/api/proposals/{card}/dismiss").status_code == 409
    assert client.post("/api/proposals/999/dismiss").status_code == 404


@pytest.mark.parametrize(
    ("command", "payload", "answer"),
    [
        ("approve", {"item_id": 1, "reason": "ok"}, "nothing is waiting"),
        ("start_run", {"seed": 42}, "Loading leads is a demo control, bottom right."),
        (
            "deliver_reply",
            {"lead_id": "L-1", "intent_id": "I-1", "body": "It is 1987."},
            "Paste the reply in the lead's full detail.",
        ),
    ],
)
def test_a_directive_the_assistant_may_not_propose_is_refused_and_leaves_no_card(
    client: TestClient,
    model: Script,
    settings: Settings,
    lead: str,
    command: str,
    payload: dict[str, Any],
    answer: str,
) -> None:
    model.tool_inputs.append(propose(command, payload))

    (closing,) = chat(client, "Do it", lead)

    assert closing["type"] == "answer" and answer in closing["answer"]
    assert command not in closing["answer"]
    (refusal,) = [e for e in events(settings, EventType.command_refused) if e.actor == "assistant"]
    assert refusal.payload.command_type == "propose_command"
    assert client.get("/api/proposals").json() == []


def test_an_empty_message_is_not_a_turn(client: TestClient) -> None:
    assert client.post("/api/chat", json={"message": ""}).status_code == 422


def test_the_proposals_table_is_the_cards_store(
    client: TestClient, model: Script, settings: Settings, lead: str
) -> None:
    proposed(client, model, lead, lead)

    db = sqlite3.connect(settings.db_path)
    assert db.execute("SELECT state, actor FROM proposals").fetchall() == [("open", "assistant")]
    db.close()
