# ABOUTME: Tests the proposal cards of A.1 and A.11: `propose_command` stores one open card and a `proposal_created` event and runs nothing, a proposal of a command the assistant must not carry is refused, and a card leaves `open` once.
# ABOUTME: Each test opens a real database at a tmp_path file and submits commands through the command layer as the assistant.
import sqlite3
from pathlib import Path

import pytest
from pydantic import JsonValue

from tests.runtime.helpers import (
    LEAD_ID,
    RULESET,
    RUN_START,
    command_environment,
    events_of,
    insert_run,
)
from uwh.runtime.commands import submit_command
from uwh.runtime.event_types import CommandRefused, EventType, ProposalCreated
from uwh.runtime.events import EventContext
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.proposals import Proposal, open_proposals, read_proposal, settle_proposal
from uwh.runtime.runs import RunEnvironment
from uwh.runtime.store import open_store
from uwh.runtime.workflow import create_lead
from uwh.skills.vertical import REFERENCE_MORNING

DECLINE: dict[str, JsonValue] = {
    "type": "decline_lead",
    "payload": {"lead_id": LEAD_ID, "reason": "outside appetite"},
    "rationale": "The producer said the building is a vacant warehouse.",
}


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db = open_store(str(tmp_path / "app.db"))
    insert_run(db)
    setup = EventContext("run-1", "replay", "workflow", RULESET, RUN_START, REFERENCE_MORNING)
    create_lead(db, setup, LEAD_ID, "web", "2026-06-29T07:00:00Z")
    db.commit()
    return db


@pytest.fixture
def env(tmp_path: Path, mailbox: MailboxClient, leadgen: LeadgenClient) -> RunEnvironment:
    return command_environment(tmp_path, mailbox, leadgen, ())


def test_a_proposal_stores_an_open_card_and_its_event_and_runs_nothing(
    db: sqlite3.Connection, env: RunEnvironment
) -> None:
    result = submit_command(db, env, "assistant", "propose_command", DECLINE)

    assert result.accepted
    (event,) = events_of(db, EventType.proposal_created)
    assert event.id == result.event_id and event.actor == "assistant" and event.lead_id == LEAD_ID
    assert isinstance(event.payload, ProposalCreated)
    assert open_proposals(db) == [
        Proposal(event.payload.proposal_id, DECLINE, "open", "assistant", event.id)
    ]
    assert db.execute("SELECT status FROM leads").fetchone() == ("received",)
    assert events_of(db, EventType.ruling_recorded) == []


@pytest.mark.parametrize(
    "proposed",
    ["approve", "reject", "propose_command", "send_routine_request", "no_such_command"],
)
def test_a_proposal_of_a_command_the_assistant_must_not_carry_is_refused_and_leaves_no_card(
    db: sqlite3.Connection, env: RunEnvironment, proposed: str
) -> None:
    result = submit_command(
        db,
        env,
        "assistant",
        "propose_command",
        {**DECLINE, "type": proposed, "payload": {"item_id": 1}},
    )

    assert not result.accepted and result.reason is not None and proposed in result.reason
    (refusal,) = events_of(db, EventType.command_refused)
    assert isinstance(refusal.payload, CommandRefused) and refusal.id == result.event_id
    assert open_proposals(db) == []
    assert events_of(db, EventType.proposal_created) == []


@pytest.mark.parametrize(
    "bad", [{"payload": "not an object"}, {"rationale": ""}, {"rationale": None}]
)
def test_a_proposal_needs_an_object_payload_and_a_rationale(
    db: sqlite3.Connection, env: RunEnvironment, bad: dict[str, JsonValue]
) -> None:
    result = submit_command(db, env, "assistant", "propose_command", {**DECLINE, **bad})

    assert not result.accepted and (result.reason or "").startswith("the payload needs")
    assert open_proposals(db) == []


def test_a_card_leaves_open_once(db: sqlite3.Connection, env: RunEnvironment) -> None:
    submit_command(db, env, "assistant", "propose_command", DECLINE)
    (card,) = open_proposals(db)

    assert settle_proposal(db, card.id, "applied")
    assert read_proposal(db, card.id) == Proposal(
        card.id, DECLINE, "applied", "assistant", card.event_id
    )
    assert open_proposals(db) == []
    assert not settle_proposal(db, card.id, "dismissed")
    assert not settle_proposal(db, 99, "dismissed")
    assert read_proposal(db, 99) is None
