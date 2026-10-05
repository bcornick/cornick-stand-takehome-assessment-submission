# ABOUTME: Tests that a lead holds several blockers with kind, owner and resume trigger, that the primary next action follows the 7.1 priority order, and that an unservable blocker or a bad observation item is refused at the write.
# ABOUTME: Each test opens a real database through open_store and reads back the blockers table and the events; one test shows the lead detail view's BlockerView refuses what the write refuses.
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from uwh.api.views import BlockerView
from uwh.runtime.event_types import BlockerDetail, BlockerKind, BlockerOwner, EventType
from uwh.runtime.events import EventContext, read_events
from uwh.runtime.store import open_store
from uwh.runtime.waits import (
    close_blocker,
    open_blocker,
    open_blocker_by_id,
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


def add_observation(db: sqlite3.Connection, status: str, lead_id: str = "L-1") -> int:
    cursor = db.execute(
        "INSERT INTO observations (lead_id, key, value_json, source, evidence_json, status)"
        " VALUES (?, 'acreage', '2', 'reply', '{}', ?)",
        (lead_id, status),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


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


def test_closing_an_unknown_or_closed_blocker_is_refused(db: sqlite3.Connection) -> None:
    blocker_id = open_blocker(db, CONTEXT, "L-1", "data", "data_team", detail())
    close_blocker(db, CONTEXT, blocker_id)
    with pytest.raises(ValueError, match="already closed"):
        close_blocker(db, CONTEXT, blocker_id)
    with pytest.raises(ValueError, match="no blocker 99"):
        close_blocker(db, CONTEXT, 99)


def test_an_open_blocker_is_found_by_its_id_and_a_closed_or_unknown_one_is_not(
    db: sqlite3.Connection,
) -> None:
    blocker_id = open_blocker(db, CONTEXT, "L-1", "data", "data_team", detail())
    found = open_blocker_by_id(db, blocker_id)
    assert found is not None
    assert (found.id, found.lead_id, found.kind, found.owner) == (
        blocker_id,
        "L-1",
        "data",
        "data_team",
    )
    assert found.detail.text == "waiting"
    close_blocker(db, CONTEXT, blocker_id)
    assert open_blocker_by_id(db, blocker_id) is None
    assert open_blocker_by_id(db, 999) is None


def test_blockers_of_another_lead_are_not_listed(db: sqlite3.Connection) -> None:
    add_lead(db, "L-2", "in_progress")
    open_blocker(db, CONTEXT, "L-2", "data", "data_team", detail())
    assert open_blockers(db, "L-1") == []


def review_detail(**changes: Any) -> BlockerDetail:
    return detail(item_kind="review", cause="late_reply", **changes)


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


def test_the_oldest_blocker_of_the_top_kind_is_primary(db: sqlite3.Connection) -> None:
    first = open_blocker(db, CONTEXT, "L-1", "data", "data_team", detail())
    open_blocker(db, CONTEXT, "L-1", "data", "data_team", detail())
    primary = primary_next_action(db, "L-1")
    assert primary is not None and primary.id == first


@pytest.mark.parametrize("status", ["quote_sent", "declined"])
def test_a_terminal_lead_has_no_primary_next_action(db: sqlite3.Connection, status: str) -> None:
    add_lead(db, "L-T", status)
    open_blocker(db, CONTEXT, "L-T", "data", "data_team", detail())
    assert primary_next_action(db, "L-T") is None


def test_the_primary_next_action_of_an_unknown_lead_is_refused(db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="no lead L-9"):
        primary_next_action(db, "L-9")


# ---- what a blocker may carry ----------------------------------------------------------------------


def test_a_pending_observation_item_is_accepted(db: sqlite3.Connection) -> None:
    observation_id = add_observation(db, "pending_review")
    blocker_id = open_blocker(
        db,
        CONTEXT,
        "L-1",
        "underwriter_review",
        "underwriter",
        detail(item_kind="observation", observation_id=observation_id),
    )
    assert [b.id for b in open_blockers(db, "L-1")] == [blocker_id]


@pytest.mark.parametrize(
    ("kind", "owner", "fields"),
    [
        ("data", "data_team", {"cause": "late_reply"}),
        ("data", "data_team", {"choice_ids": ["c1"]}),
        ("underwriter_question", "underwriter", {}),
        ("underwriter_review", "underwriter", {"item_kind": "draft"}),
    ],
)
def test_a_blocker_the_rule_refuses_is_refused_at_the_write_and_by_the_view(
    db: sqlite3.Connection, kind: BlockerKind, owner: BlockerOwner, fields: dict[str, Any]
) -> None:
    blocker_detail = detail(**fields)
    with pytest.raises(ValueError):
        open_blocker(db, CONTEXT, "L-1", kind, owner, blocker_detail)
    with pytest.raises(ValidationError):
        BlockerView(
            item_id=1,
            kind=kind,
            owner=owner,
            detail=blocker_detail,
            observation=None,
            held_draft_payload_hash=None,
        )
    assert db.execute("SELECT COUNT(*) FROM blockers").fetchone() == (0,)
    assert read_events(db) == []


@pytest.mark.parametrize("status", ["accepted", "rejected"])
def test_an_observation_item_for_an_observation_not_pending_is_refused(
    db: sqlite3.Connection, status: str
) -> None:
    observation_id = add_observation(db, status)
    blocker_detail = detail(item_kind="observation", observation_id=observation_id)
    with pytest.raises(ValueError, match="not a pending_review"):
        open_blocker(db, CONTEXT, "L-1", "underwriter_review", "underwriter", blocker_detail)
    assert read_events(db) == []


def test_an_observation_item_for_a_missing_observation_is_refused(db: sqlite3.Connection) -> None:
    blocker_detail = detail(item_kind="observation", observation_id=41)
    with pytest.raises(ValueError, match="not a pending_review"):
        open_blocker(db, CONTEXT, "L-1", "underwriter_review", "underwriter", blocker_detail)


def test_an_observation_item_for_another_leads_observation_is_refused(
    db: sqlite3.Connection,
) -> None:
    add_lead(db, "L-2", "in_progress")
    observation_id = add_observation(db, "pending_review", "L-2")
    blocker_detail = detail(item_kind="observation", observation_id=observation_id)
    with pytest.raises(ValueError, match=f"observation {observation_id} is not lead L-1's"):
        open_blocker(db, CONTEXT, "L-1", "underwriter_review", "underwriter", blocker_detail)
    assert db.execute("SELECT COUNT(*) FROM blockers").fetchone() == (0,)
    assert read_events(db) == []
