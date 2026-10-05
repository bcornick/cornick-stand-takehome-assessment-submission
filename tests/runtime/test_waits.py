# ABOUTME: Tests that a lead holds several blockers with kind, owner and resume trigger, that the primary next action follows the 7.1 priority order, and that a blocker the lead detail view would refuse is refused at the write.
# ABOUTME: Each test opens a real database through open_store and reads back the blockers table and the events; the view check validates every accepted blocker as the API's BlockerView.
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from uwh.api.views import BlockerView, FactView, QuestionItem
from uwh.runtime.event_types import BlockerDetail, BlockerKind, BlockerOwner, EventType
from uwh.runtime.events import EventContext, read_events
from uwh.runtime.store import open_store
from uwh.runtime.waits import close_blocker, open_blocker, open_blockers, primary_next_action

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


# ---- what the lead detail view would refuse ------------------------------------------------------

Case = tuple[BlockerKind, BlockerOwner, dict[str, Any]]

ACCEPTED: dict[str, Case] = {
    "producer reply": ("producer_reply", "producer", {"intent_id": "I-1"}),
    "data": ("data", "data_team", {}),
    "question": ("underwriter_question", "underwriter", {"choice_ids": ["c1"]}),
    "delivery unknown": ("delivery_unknown", "underwriter", {"item_kind": "delivery_unknown"}),
    "draft review": (
        "underwriter_review",
        "underwriter",
        {"item_kind": "draft", "intent_id": "I-1"},
    ),
    "no contact route": ("underwriter_review", "underwriter", {"item_kind": "no_contact_route"}),
    "late reply review": (
        "underwriter_review",
        "underwriter",
        {"item_kind": "review", "cause": "late_reply"},
    ),
    "persistent review": (
        "underwriter_review",
        "underwriter",
        {"item_kind": "review", "cause": "round_limit", "cause_persists": True},
    ),
    "held draft review": (
        "underwriter_review",
        "underwriter",
        {"item_kind": "review", "cause": "draft_held_by_stop", "intent_id": "I-1"},
    ),
    "pending observation": (
        "underwriter_review",
        "underwriter",
        {"item_kind": "observation"},  # observation_id is added by the test
    ),
}

REFUSED: dict[str, Case] = {
    "a cause on a blocker that is not a review": (
        "underwriter_review",
        "underwriter",
        {"item_kind": "draft", "intent_id": "I-1", "cause": "late_reply"},
    ),
    "a cause on a data blocker": ("data", "data_team", {"cause": "late_reply"}),
    "an item kind on a producer reply": ("producer_reply", "producer", {"item_kind": "draft"}),
    "an item kind on a question": ("underwriter_question", "underwriter", {"item_kind": "review"}),
    "delivery_unknown without its item kind": ("delivery_unknown", "underwriter", {}),
    "delivery_unknown with the wrong item kind": (
        "delivery_unknown",
        "underwriter",
        {"item_kind": "draft"},
    ),
    "a review without an item kind": ("underwriter_review", "underwriter", {}),
    "a review with the item kind delivery_unknown": (
        "underwriter_review",
        "underwriter",
        {"item_kind": "delivery_unknown"},
    ),
    "a draft review without its draft": (
        "underwriter_review",
        "underwriter",
        {"item_kind": "draft"},
    ),
    "a review without a cause": ("underwriter_review", "underwriter", {"item_kind": "review"}),
    "a persistent cause not marked persistent": (
        "underwriter_review",
        "underwriter",
        {"item_kind": "review", "cause": "round_limit"},
    ),
    "a non-persistent cause marked persistent": (
        "underwriter_review",
        "underwriter",
        {"item_kind": "review", "cause": "late_reply", "cause_persists": True},
    ),
    "cause_persists outside a review": (
        "underwriter_review",
        "underwriter",
        {"item_kind": "draft", "intent_id": "I-1", "cause_persists": True},
    ),
    "a held draft's review without its draft": (
        "underwriter_review",
        "underwriter",
        {"item_kind": "review", "cause": "draft_held_class_off"},
    ),
    "an observation item without observation_id": (
        "underwriter_review",
        "underwriter",
        {"item_kind": "observation"},
    ),
}


# Refused by `open_blocker` alone: no view model states these rules. `BlockerView` does not read
# `detail.choice_ids`, and `QuestionItem` is the only view that does.
RUNTIME_ONLY_REFUSED: dict[str, Case] = {
    "choice_ids on a data blocker": ("data", "data_team", {"choice_ids": ["c1"]}),
    "choice_ids on a review": (
        "underwriter_review",
        "underwriter",
        {"item_kind": "review", "cause": "late_reply", "choice_ids": ["c1"]},
    ),
    "choice_ids on a producer reply": ("producer_reply", "producer", {"choice_ids": ["c1"]}),
}


def view_of(
    kind: BlockerKind,
    owner: BlockerOwner,
    blocker_detail: BlockerDetail,
    observation: FactView | None,
) -> BlockerView:
    held = blocker_detail.cause in ("draft_held_by_stop", "draft_held_class_off")
    return BlockerView(
        item_id=1,
        kind=kind,
        owner=owner,
        detail=blocker_detail,
        observation=observation,
        held_draft_payload_hash="h" * 64 if held else None,
    )


def pending_fact(observation_id: int) -> FactView:
    return FactView(
        key="acreage",
        value=2,
        source="reply",
        status="pending_review",
        confirmed=False,
        evidence={},
        observation_id=observation_id,
        is_stub=False,
    )


@pytest.mark.parametrize("name", ACCEPTED)
def test_every_blocker_waits_accepts_validates_as_a_blocker_view(
    db: sqlite3.Connection, name: str
) -> None:
    kind, owner, fields = ACCEPTED[name]
    observation = None
    if fields.get("item_kind") == "observation":
        observation_id = add_observation(db, "pending_review")
        fields = {**fields, "observation_id": observation_id}
        observation = pending_fact(observation_id)
    blocker_detail = detail(**fields)
    open_blocker(db, CONTEXT, "L-1", kind, owner, blocker_detail)
    assert view_of(kind, owner, blocker_detail, observation).kind == kind


@pytest.mark.parametrize("name", REFUSED)
def test_every_blocker_the_view_refuses_is_refused_at_the_write(
    db: sqlite3.Connection, name: str
) -> None:
    kind, owner, fields = REFUSED[name]
    blocker_detail = detail(**fields)
    with pytest.raises(ValidationError):
        view_of(kind, owner, blocker_detail, None)
    with pytest.raises(ValueError):
        open_blocker(db, CONTEXT, "L-1", kind, owner, blocker_detail)
    assert db.execute("SELECT COUNT(*) FROM blockers").fetchone() == (0,)
    assert read_events(db) == []


@pytest.mark.parametrize("status", ["accepted", "rejected"])
def test_an_observation_item_for_an_observation_not_pending_is_refused_by_both(
    db: sqlite3.Connection, status: str
) -> None:
    observation_id = add_observation(db, status)
    blocker_detail = detail(item_kind="observation", observation_id=observation_id)
    fact = pending_fact(observation_id).model_copy(update={"status": status})
    with pytest.raises(ValidationError):
        view_of("underwriter_review", "underwriter", blocker_detail, fact)
    with pytest.raises(ValueError, match="not a pending_review"):
        open_blocker(db, CONTEXT, "L-1", "underwriter_review", "underwriter", blocker_detail)


def test_an_observation_item_for_a_missing_observation_is_refused(db: sqlite3.Connection) -> None:
    blocker_detail = detail(item_kind="observation", observation_id=41)
    with pytest.raises(ValueError, match="not a pending_review"):
        open_blocker(db, CONTEXT, "L-1", "underwriter_review", "underwriter", blocker_detail)


@pytest.mark.parametrize("name", RUNTIME_ONLY_REFUSED)
def test_every_blocker_only_the_runtime_refuses_is_refused_at_the_write(
    db: sqlite3.Connection, name: str
) -> None:
    kind, owner, fields = RUNTIME_ONLY_REFUSED[name]
    with pytest.raises(ValueError, match="choice_ids"):
        open_blocker(db, CONTEXT, "L-1", kind, owner, detail(**fields))
    assert db.execute("SELECT COUNT(*) FROM blockers").fetchone() == (0,)
    assert read_events(db) == []


def test_a_question_without_choices_is_refused_by_both(db: sqlite3.Connection) -> None:
    blocker_detail = detail()
    with pytest.raises(ValidationError):
        QuestionItem(
            item_id=1,
            kind="underwriter_question",
            owner="underwriter",
            detail=blocker_detail,
            observation=None,
            held_draft_payload_hash=None,
            type="question",
            lead_id="L-1",
            choices=[],
        )
    with pytest.raises(ValueError, match="choice_ids"):
        open_blocker(db, CONTEXT, "L-1", "underwriter_question", "underwriter", blocker_detail)
    assert db.execute("SELECT COUNT(*) FROM blockers").fetchone() == (0,)
    assert read_events(db) == []


def test_an_observation_item_for_another_leads_observation_is_refused(
    db: sqlite3.Connection,
) -> None:
    # `BlockerView` compares only the observation ids, so no view refuses this; the write does.
    add_lead(db, "L-2", "in_progress")
    observation_id = add_observation(db, "pending_review", "L-2")
    blocker_detail = detail(item_kind="observation", observation_id=observation_id)
    with pytest.raises(ValueError, match=f"observation {observation_id} is not lead L-1's"):
        open_blocker(db, CONTEXT, "L-1", "underwriter_review", "underwriter", blocker_detail)
    assert db.execute("SELECT COUNT(*) FROM blockers").fetchone() == (0,)
    assert read_events(db) == []
