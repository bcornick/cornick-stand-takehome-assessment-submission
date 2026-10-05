# ABOUTME: Tests that a lead holds several blockers with kind, owner and resume trigger, that the primary next action follows the 7.1 priority order.
# ABOUTME: Each test opens a real database through open_store and reads back the blockers table and the events.
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from uwh.runtime.event_types import BlockerDetail, EventType
from uwh.runtime.events import EventContext, read_events
from uwh.runtime.store import open_store
from uwh.runtime.waits import (
    close_blocker,
    open_blocker,
    open_blockers,
    primary_next_action,
)

NOW = datetime(2026, 6, 29, 8, 0, 0, tzinfo=UTC)
CONTEXT = EventContext("run-1", "replay", "workflow", "r" * 64, NOW, NOW)


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db = open_store(str(tmp_path / "app.db"))
    add_lead(db, "L-1", "in_progress")
    return db


def add_lead(db: sqlite3.Connection, lead_id: str, status: str) -> None:
    db.execute(
        "INSERT INTO leads (lead_id, run_id, source, received_at, status, revision)"
        " VALUES (?, 'run-1', 'web', '2026-06-29T07:00:00Z', ?, 0)",
        (lead_id, status),
    )


def detail(**changes: Any) -> BlockerDetail:
    fields: dict[str, Any] = {"resume_trigger": "a reply arrives", "text": "waiting"}
    return BlockerDetail(**{**fields, **changes})


def test_a_lead_holds_several_blockers_each_with_kind_owner_and_resume_trigger(
    db: sqlite3.Connection,
) -> None:
    reply = open_blocker(db, CONTEXT, "L-1", "producer_reply", "producer", detail(intent_id="I-1"))
    data = open_blocker(
        db, CONTEXT, "L-1", "data", "data_team", detail(resume_trigger="the fetch returns")
    )
    held = open_blockers(db, "L-1")
    assert [(b.id, b.kind, b.owner) for b in held] == [
        (reply, "producer_reply", "producer"),
        (data, "data", "data_team"),
    ]
    assert [b.detail.resume_trigger for b in held] == ["a reply arrives", "the fetch returns"]
    assert held[0].detail.intent_id == "I-1"


def test_opening_a_blocker_writes_its_event_and_records_the_event_id(
    db: sqlite3.Connection,
) -> None:
    blocker_id = open_blocker(db, CONTEXT, "L-1", "data", "data_team", detail())
    (event,) = read_events(db, lead_id="L-1")
    assert event.type is EventType.blocker_opened
    assert event.payload.model_dump()["blocker_id"] == blocker_id
    row = db.execute(
        "SELECT kind, owner, detail_json, opened_event_id, closed_event_id FROM blockers"
    ).fetchone()
    assert row[:2] == ("data", "data_team")
    assert json.loads(row[2])["resume_trigger"] == "a reply arrives"
    assert row[3:] == (event.id, None)


def test_closing_a_blocker_writes_its_event_and_removes_it_from_the_open_list(
    db: sqlite3.Connection,
) -> None:
    kept = open_blocker(db, CONTEXT, "L-1", "data", "data_team", detail())
    closed = open_blocker(db, CONTEXT, "L-1", "producer_reply", "producer", detail())
    close_blocker(db, CONTEXT, closed)
    assert [b.id for b in open_blockers(db, "L-1")] == [kept]
    event = read_events(db, lead_id="L-1")[-1]
    assert event.type is EventType.blocker_closed
    assert event.payload.model_dump() == {"blocker_id": closed, "kind": "producer_reply"}
    row = db.execute("SELECT closed_event_id FROM blockers WHERE id = ?", (closed,)).fetchone()
    assert row == (event.id,)


def test_the_primary_next_action_is_the_highest_priority_open_blocker(
    db: sqlite3.Connection,
) -> None:
    opened: dict[str, int] = {}
    # opened in an order that is neither the priority order nor its reverse
    for kind, owner, item in (
        ("data", "data_team", {}),
        ("delivery_unknown", "underwriter", {"item_kind": "delivery_unknown"}),
        ("producer_reply", "producer", {}),
        ("underwriter_review", "underwriter", {"item_kind": "review", "cause": "late_reply"}),
        ("underwriter_question", "underwriter", {"choice_ids": ["c1"]}),
    ):
        opened[kind] = open_blocker(db, CONTEXT, "L-1", kind, owner, detail(**item))  # type: ignore[arg-type]
    order = [
        "delivery_unknown",
        "underwriter_question",
        "underwriter_review",
        "data",
        "producer_reply",
    ]
    for kind in order:
        primary = primary_next_action(db, "L-1")
        assert primary is not None
        assert primary.id == opened[kind]
        close_blocker(db, CONTEXT, opened[kind])
    assert primary_next_action(db, "L-1") is None


@pytest.mark.parametrize("status", ["quote_sent", "declined"])
def test_a_terminal_lead_has_no_primary_next_action(db: sqlite3.Connection, status: str) -> None:
    add_lead(db, "L-T", status)
    open_blocker(db, CONTEXT, "L-T", "data", "data_team", detail())
    assert primary_next_action(db, "L-T") is None
