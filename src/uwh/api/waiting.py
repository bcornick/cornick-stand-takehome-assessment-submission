# ABOUTME: What a lead is waiting for, as the queue row and the lead's drafts state it: the decision an underwriter blocker asks for, when each message went out and what a request asks.
# ABOUTME: Both are read from stored state: the blocker and its draft, and the `message_sent` events.
import sqlite3
from datetime import datetime

from uwh.rules.confirmations import reported_fields
from uwh.rules.registry import FactField
from uwh.runtime.event_types import REQUEST_KINDS, EventType, MessageSent, ReviewCause
from uwh.runtime.events import read_events
from uwh.runtime.waits import Blocker

# The decision of a draft review, by the kind of message the draft is.
_DRAFT_DECISIONS = {
    "decline_notice": "Review decline notice",
    "quote_packet": "Review quote",
    "routine_request": "Review request",
    "sensitive_request": "Review request",
}
_CAUSE_DECISIONS: dict[ReviewCause, str] = {
    "late_reply": "Review a reply",
    "unread_reply": "Review a reply",
    "off_topic_reply": "Review a reply",
    "declining_reply": "Review a reply",
    "reply_after_terminal_status": "Review a reply",
    "round_limit": "Review the round limit",
    "identity_score_missing": "Review the identity score",
    "identity_score_unsupported": "Review the identity score",
}
# A choice is named by its subject; the id's own words stand for a subject not listed here.
_CHOICE_SUBJECTS = {"I13.fire_fail": "Fire simulation"}


def _choice_decision(choice_id: str) -> str:
    subject = _CHOICE_SUBJECTS.get(choice_id)
    if subject is None:
        subject = choice_id.split(".", 1)[1].replace("_", " ").capitalize()
    return f"{subject} choice"


def decision_phrase(db: sqlite3.Connection, blocker: Blocker) -> str:
    """What the underwriter is asked to decide, in a few words, for an underwriter blocker."""
    detail = blocker.detail
    if blocker.kind == "underwriter_question":
        return _choice_decision(detail.choice_ids[0])
    if blocker.kind == "delivery_unknown":
        return "Check a delivery"
    if detail.item_kind == "draft":
        (kind,) = db.execute(
            "SELECT kind FROM intents WHERE id = ?", (detail.intent_id,)
        ).fetchone()
        return _DRAFT_DECISIONS[kind]
    if detail.item_kind == "observation":
        return "Review a reply's value"
    if detail.item_kind == "no_contact_route":
        return "Find a contact route"
    assert detail.cause is not None  # refuse_unservable_blocker requires a review's cause
    return _CAUSE_DECISIONS[detail.cause]


def sent_times(db: sqlite3.Connection, lead_id: str) -> dict[str, datetime]:
    """The simulated time each of the lead's messages went out, by intent id."""
    return {
        e.payload.intent_id: e.sim_ts
        for e in read_events(db, lead_id=lead_id)
        if e.type == EventType.message_sent and isinstance(e.payload, MessageSent)
    }


def open_request(db: sqlite3.Connection, lead_id: str) -> tuple[int, datetime | None] | None:
    """The round and send time (None when no send is recorded) of the lead's latest request to the producer that is out, or None."""
    placeholders = ", ".join("?" for _ in REQUEST_KINDS)
    row = db.execute(
        f"SELECT id, round FROM intents WHERE lead_id = ? AND state = 'sent'"
        f" AND kind IN ({placeholders}) ORDER BY round DESC, rowid DESC LIMIT 1",
        (lead_id, *REQUEST_KINDS),
    ).fetchone()
    if row is None:
        return None
    return row[1], sent_times(db, lead_id).get(row[0])


def ask_label(ask_id: str, fields: dict[str, FactField]) -> str:
    """An ask as the underwriter reads it: the field's label, a catalogue question's wording, or
    "Confirm" with the labels of the fields a confirmation reports."""
    for key in (ask_id, f"q:{ask_id}"):
        if key in fields:
            return fields[key].label
    labels = [fields[name].label for name in reported_fields(ask_id)]
    listed = labels[0] if len(labels) == 1 else f"{', '.join(labels[:-1])} and {labels[-1]}"
    return f"Confirm {listed}"
