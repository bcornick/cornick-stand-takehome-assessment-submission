# ABOUTME: Tests the reply to the confirmation in lead 004's request (7.3 rules 3 and 6): a reply that restates the zero residents closes the conflict and the producer gets one consolidated second request, and a reply that changes the number raises an underwriter review and leaves the conflict open.
# ABOUTME: The app runs in process with the real steps; the model's reading is a hand-made recording of the reply, since these tests are of the ledger's rules and not of the model.
import json
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import REGISTRY, first_pass
from uwh.rules.registry import load_registry
from uwh.runtime.event_types import EventType
from uwh.runtime.events import read_events
from uwh.runtime.facts import effective_facts, open_conflicts
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.recordings import Exchange, write_recording
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blockers
from uwh.settings import Settings
from uwh.skills.read_reply import skill

LEAD_004 = "LEAD-00000042-004"
CONFIRMATION = "no_residents_in_primary_home"


@pytest.fixture
def app(
    settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient, tmp_path: Path
) -> Iterator[TestClient]:
    with first_pass(replace(settings, recordings_dir=str(tmp_path)), leadgen, mailbox) as client:
        yield client


@pytest.fixture
def db(settings: Settings) -> Iterator[sqlite3.Connection]:
    store = open_store(settings.db_path)
    yield store
    store.close()


def reply_to_the_confirmation(
    app: TestClient, db: sqlite3.Connection, tmp_path: Path, body: str, value: int, quote: str
) -> None:
    """Deliver a reply that answers only the confirmation, with the reading a model would give."""
    (intent_id, ask_ids) = db.execute(
        "SELECT id, ask_ids_json FROM intents WHERE lead_id = ?", (LEAD_004,)
    ).fetchone()
    assert CONFIRMATION in json.loads(ask_ids)
    asks = skill.open_asks(
        json.loads(ask_ids),
        load_registry(str(REGISTRY)),
        [c.opened for c in open_conflicts(db, LEAD_004)],
    )
    call = skill.forced_call(skill.ReadReplyInput(body=body, asks=asks))
    key = call.recording_key
    tool_input: dict[str, Any] = {
        "classification": "answers_some",
        "candidates": [
            {
                "ask_id": CONFIRMATION,
                "field": "number_of_residents",
                "value": value,
                "quote": quote,
            }
        ],
    }
    write_recording(
        tmp_path,
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
    answer = app.post(
        "/api/replies", json={"lead_id": LEAD_004, "intent_id": intent_id, "body": body}
    ).json()
    assert answer["accepted"] is True, answer


def test_a_reply_that_restates_the_zero_residents_closes_the_conflict_and_the_rest_is_asked_again(
    app: TestClient, db: sqlite3.Connection, mailbox: MailboxClient, tmp_path: Path
) -> None:
    reply_to_the_confirmation(
        app, db, tmp_path, "Zero is right: 0 people live there, it is a second home.", 0, "0 people"
    )

    assert open_conflicts(db, LEAD_004) == []
    fact = effective_facts(db, LEAD_004)["number_of_residents"]
    assert (fact.value, fact.confirmed, fact.source) == (0, True, "submitted")
    assert EventType.conflict_closed in [e.type for e in read_events(db, lead_id=LEAD_004)]
    # One consolidated second request holds what the reply left unanswered, and not the confirmation.
    requests = sorted((m["metadata"]["round"], m["body"]) for m in mailbox.list_for_lead(LEAD_004))
    assert [round_ for round_, _ in requests] == [1, 2]
    assert "Can you confirm that number?" not in requests[1][1]
    assert "What Coverage A (dwelling) amount is requested?" in requests[1][1]


def test_a_reply_that_changes_the_number_raises_a_review_and_leaves_the_conflict_open(
    app: TestClient, db: sqlite3.Connection, tmp_path: Path
) -> None:
    reply_to_the_confirmation(app, db, tmp_path, "Actually 2 people live there.", 2, "2 people")

    assert [c.validator for c in open_conflicts(db, LEAD_004)] == [CONFIRMATION]
    assert effective_facts(db, LEAD_004)["number_of_residents"].value == 0
    (review,) = [b for b in open_blockers(db, LEAD_004) if b.detail.item_kind == "observation"]
    assert "2" in review.detail.text
