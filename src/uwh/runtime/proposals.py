# ABOUTME: The proposal cards of A.1: a `propose_command` stores one open card and its `proposal_created` event, and a card leaves `open` once, as applied or dismissed.
# ABOUTME: A card holds `{type, payload, rationale}` and executes nothing; the underwriter applies it by submitting the proposed command.
import json
import sqlite3
from dataclasses import dataclass
from typing import Literal

from pydantic import JsonValue

from uwh.runtime.event_types import EventType, ProposalCreated, ProposalState
from uwh.runtime.events import EventContext, append_event
from uwh.runtime.workflow import unit_of_work


@dataclass(frozen=True)
class Proposal:
    id: int
    payload: dict[str, JsonValue]  # {type, payload, rationale}
    state: ProposalState
    lead_id: str | None  # the lead of the card's `proposal_created` event


# The commands a card may hold. `approve` and `reject` are the underwriter's own decisions (A.11);
# `start_run` and `deliver_reply` belong to other controls of the page.
PROPOSABLE = ("edit_draft", "record_ruling", "resolve_fact", "decline_lead")


def is_proposable(command_type: str) -> bool:
    return command_type in PROPOSABLE


def create_proposal(
    db: sqlite3.Connection,
    context: EventContext,
    payload: dict[str, JsonValue],
    lead_id: str | None,
) -> int:
    """Store an open card for `payload` and write `proposal_created`; return the event id. The caller
    owns the transaction."""
    cursor = db.execute(
        "INSERT INTO proposals (payload_json, state, actor) VALUES (?, 'open', ?)",
        (json.dumps(payload), context.actor),
    )
    proposal_id = cursor.lastrowid
    assert proposal_id is not None  # an INSERT always sets it
    event_id = append_event(
        db,
        context,
        EventType.proposal_created,
        ProposalCreated(proposal_id=proposal_id),
        lead_id=lead_id,
    )
    db.execute("UPDATE proposals SET event_id = ? WHERE id = ?", (event_id, proposal_id))
    return event_id


# A card with the lead of its `proposal_created` event; the `proposals` table holds no lead.
_SELECT = (
    "SELECT p.id, p.payload_json, p.state, e.lead_id"
    " FROM proposals p LEFT JOIN events e ON e.id = p.event_id"
)


def _proposal(row: tuple[int, str, ProposalState, str | None]) -> Proposal:
    return Proposal(row[0], json.loads(row[1]), row[2], row[3])


def read_proposal(db: sqlite3.Connection, proposal_id: int) -> Proposal | None:
    row = db.execute(f"{_SELECT} WHERE p.id = ?", (proposal_id,)).fetchone()
    return None if row is None else _proposal(row)


def open_proposals(db: sqlite3.Connection) -> list[Proposal]:
    """The cards still open, oldest first."""
    rows = db.execute(f"{_SELECT} WHERE p.state = 'open' ORDER BY p.id").fetchall()
    return [_proposal(row) for row in rows]


def settle_proposal(
    db: sqlite3.Connection, proposal_id: int, state: Literal["applied", "dismissed"]
) -> bool:
    """Move an open card to `state`. False when there is no such card or it is not open."""
    with unit_of_work(db):
        moved = db.execute(
            "UPDATE proposals SET state = ? WHERE id = ? AND state = 'open'",
            (state, proposal_id),
        )
    return moved.rowcount == 1
