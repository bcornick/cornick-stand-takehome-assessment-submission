# ABOUTME: Tests the chat read tools: the events of a lead come with their ids and only that lead's, the summary holds status, facts and open items, and the open items span every lead.
# ABOUTME: Each test builds a real database at a tmp_path file through the runtime's own writers.
import sqlite3
from pathlib import Path

import pytest

from tests.runtime.helpers import RULESET, RUN_START, insert_run
from uwh.chat.tools import EVENT_LIMIT, lead_events, lead_summary, open_items
from uwh.runtime.event_types import BlockerDetail, EventType, LeadReceived
from uwh.runtime.events import EventContext, append_event
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blocker
from uwh.runtime.workflow import create_lead
from uwh.skills.vertical import REFERENCE_MORNING

SETUP = EventContext("run-1", "replay", "workflow", RULESET, RUN_START, REFERENCE_MORNING)


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db = open_store(str(tmp_path / "app.db"))
    insert_run(db)
    create_lead(db, SETUP, "L-1", "web", "2026-06-29T07:00:00Z")
    create_lead(db, SETUP, "L-2", "web", "2026-06-29T08:00:00Z")
    open_blocker(
        db,
        SETUP,
        "L-2",
        "underwriter_review",
        "underwriter",
        BlockerDetail(
            item_kind="no_contact_route", resume_trigger="a contact is given", text="No contact."
        ),
    )
    db.commit()
    return db


def test_the_events_of_a_lead_carry_their_ids_and_are_that_leads_only(
    db: sqlite3.Connection,
) -> None:
    ids = [r[0] for r in db.execute("SELECT id FROM events WHERE lead_id = 'L-1'")]

    shown = lead_events(db, "L-1")["events"]

    assert [event["id"] for event in shown] == ids
    assert shown[0]["type"] == "lead_received" and shown[0]["actor"] == "workflow"
    assert "web" in shown[0]["summary"]


def test_only_the_latest_events_are_shown(db: sqlite3.Connection) -> None:
    for _ in range(EVENT_LIMIT + 5):
        append_event(
            db,
            SETUP,
            EventType.lead_received,
            LeadReceived(source="x", received_at="y"),
            lead_id="L-1",
        )

    shown = lead_events(db, "L-1")["events"]

    assert len(shown) == EVENT_LIMIT
    assert shown[-1]["id"] == max(r[0] for r in db.execute("SELECT id FROM events"))


def test_a_lead_that_does_not_exist_is_named_in_an_error(db: sqlite3.Connection) -> None:
    assert "L-9" in lead_events(db, "L-9")["error"]
    assert "L-9" in lead_summary(db, "L-9")["error"]


def test_the_summary_holds_the_status_and_the_open_items_of_the_lead(
    db: sqlite3.Connection,
) -> None:
    summary = lead_summary(db, "L-2")

    assert summary["status"] == "received" and summary["lead_id"] == "L-2"
    assert [item["text"] for item in summary["open_items"]] == ["No contact."]
    assert lead_summary(db, "L-1")["open_items"] == []


def test_the_open_items_span_every_lead(db: sqlite3.Connection) -> None:
    (item,) = open_items(db)["open_items"]

    assert item["lead_id"] == "L-2" and item["kind"] == "underwriter_review"
