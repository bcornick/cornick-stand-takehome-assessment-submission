# ABOUTME: Tests the chat lookups: the events of a lead are that lead's only and numbered, an item is cited by the event that opened it, a lead is found by the end of its id, and the queue's open items span every lead.
# ABOUTME: Each test builds a real database at a tmp_path file through the runtime's own writers.
import sqlite3
from pathlib import Path

import pytest

from tests.runtime.helpers import RULESET, RUN_START, insert_run
from uwh.chat.tools import References, lead_events, lead_summary, look_up, queue_summary
from uwh.runtime.event_types import BlockerDetail
from uwh.runtime.events import EventContext
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


def test_the_events_of_a_lead_are_that_leads_only_and_each_is_numbered(
    db: sqlite3.Connection,
) -> None:
    ids = [r[0] for r in db.execute("SELECT id FROM events WHERE lead_id = 'L-1'")]
    references = References()

    lookup = lead_events(db, "L-1", references)

    shown = lookup.shown["events"]
    assert [c.id for c in references.resolve(event["ref"] for event in shown)] == ids
    assert shown[0]["type"] == "lead_received" and shown[0]["actor"] == "workflow"
    assert "web" in shown[0]["summary"] and "id" not in shown[0]
    assert lookup.summary == "Read the events of lead 1: 1 events"


def test_a_thing_shown_twice_keeps_its_number(db: sqlite3.Connection) -> None:
    references = References()

    first = lead_events(db, "L-1", references).shown["events"]
    again = lead_events(db, "L-1", references).shown["events"]

    assert [event["ref"] for event in first] == [event["ref"] for event in again] == [1]


def test_a_lead_is_found_by_the_end_of_its_id_and_an_unknown_one_is_an_error(
    db: sqlite3.Connection,
) -> None:
    assert look_up(db, "lead_summary", "2", References()).shown["lead_id"] == "L-2"
    assert "L-9" in look_up(db, "lead_events", "L-9", References()).shown["error"]
    # The empty name ends both ids, so it names no one lead.
    assert "error" in look_up(db, "lead_summary", "", References()).shown


def test_the_summary_holds_the_status_and_cites_an_item_by_the_event_that_opened_it(
    db: sqlite3.Connection,
) -> None:
    references = References()
    (opened,) = db.execute("SELECT opened_event_id FROM blockers").fetchone()

    summary = lead_summary(db, "L-2", references).shown

    assert summary["status"] == "received" and summary["lead_id"] == "L-2"
    (item,) = summary["open_items"]
    assert item["text"] == "No contact."
    (cited,) = references.resolve([item["ref"]])
    assert (cited.lead_id, cited.kind, cited.id) == ("L-2", "event", opened)
    assert lead_summary(db, "L-1", References()).shown["open_items"] == []


def test_the_queue_summary_spans_every_lead_and_leaves_out_a_wait_on_the_producer(
    db: sqlite3.Connection,
) -> None:
    open_blocker(
        db,
        SETUP,
        "L-1",
        "producer_reply",
        "producer",
        BlockerDetail(resume_trigger="the producer replies", text="Waiting for the producer."),
    )
    db.commit()

    lookup = queue_summary(db, References())

    (item,) = lookup.shown["open_items"]
    assert item["lead_id"] == "L-2" and item["kind"] == "underwriter_review"
    assert lookup.shown["summary"]["waiting_on_underwriter"] == 1
    assert lookup.summary == "Read the queue: 1 open items on 1 leads"
