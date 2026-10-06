# ABOUTME: The chat panel's read tools (section 11): the recent events of a lead, a lead's summary and every open item, each answered from the stored state.
# ABOUTME: A tool returns plain JSON for the model; the events carry their ids, which an answer cites. The open items are the ones the pages list.
import sqlite3
from collections.abc import Callable
from typing import Any

from uwh.api.leads import open_items as open_item_rows
from uwh.api.views import Item
from uwh.runtime.events import read_events
from uwh.runtime.facts import effective_facts
from uwh.skills.steps import lead_label

# How many of a lead's latest events a tool shows, and how much of each event's payload.
EVENT_LIMIT = 40
SUMMARY_CHARACTERS = 240


def _lead_exists(db: sqlite3.Connection, lead_id: str) -> bool:
    return db.execute("SELECT 1 FROM leads WHERE lead_id = ?", (lead_id,)).fetchone() is not None


def lead_events(db: sqlite3.Connection, lead_id: str) -> dict[str, Any]:
    """The latest events of the lead, oldest first, each with its id."""
    if not _lead_exists(db, lead_id):
        return {"error": f"there is no lead {lead_id}"}
    events = read_events(db, lead_id=lead_id)[-EVENT_LIMIT:]
    return {
        "events": [
            {
                "id": event.id,
                "type": event.type.value,
                "actor": event.actor,
                "summary": event.payload.model_dump_json()[:SUMMARY_CHARACTERS],
            }
            for event in events
        ]
    }


def _item(item: Item) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "lead_id": item.lead_id,
        "kind": item.kind,
        "text": item.detail.text,
    }


def lead_summary(db: sqlite3.Connection, lead_id: str) -> dict[str, Any]:
    """The lead's status, effective facts and open items."""
    row = db.execute("SELECT status FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    if row is None:
        return {"error": f"there is no lead {lead_id}"}
    return {
        "lead_id": lead_id,
        "label": lead_label(db, lead_id),
        "status": row[0],
        "facts": {key: fact.value for key, fact in effective_facts(db, lead_id).items()},
        "open_items": [_item(item) for item in open_item_rows(db) if item.lead_id == lead_id],
    }


def open_items(db: sqlite3.Connection) -> dict[str, Any]:
    """Every open item of every lead."""
    return {"open_items": [_item(item) for item in open_item_rows(db)]}


# The read actions of a chat step and the functions that answer them; `lead_id` is the lead the
# step names, which `open_items` ignores.
READ_TOOLS: dict[str, Callable[[sqlite3.Connection, str], dict[str, Any]]] = {
    "lead_events": lead_events,
    "lead_summary": lead_summary,
    "open_items": lambda db, _lead_id: open_items(db),
}
