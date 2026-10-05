# ABOUTME: The waiting primitive of 7.1: a blocker row with a kind, an owner and a resume trigger; opens and closes blockers, lists a lead's open ones and names its primary next action.
# ABOUTME: Opening refuses what `refuse_unservable_blocker` refuses and an observation item whose observation is not this lead's pending one, so a bad write fails at the write; every change writes its event and the caller commits.
import sqlite3
from dataclasses import dataclass

from uwh.runtime.event_types import (
    BlockerClosed,
    BlockerDetail,
    BlockerKind,
    BlockerOpened,
    BlockerOwner,
    EventType,
)
from uwh.runtime.events import EventContext, append_event
from uwh.skills.vertical import (
    BLOCKER_KINDS_BY_PRIORITY,
    TERMINAL_STATUSES,
    refuse_unservable_blocker,
)


@dataclass(frozen=True)
class Blocker:
    id: int
    lead_id: str
    kind: BlockerKind
    owner: BlockerOwner
    detail: BlockerDetail


def _require_pending_observation(
    db: sqlite3.Connection, lead_id: str, observation_id: int | None
) -> None:
    if observation_id is None:
        raise ValueError("an observation item names its observation: observation_id")
    row = db.execute(
        "SELECT lead_id, status FROM observations WHERE id = ?", (observation_id,)
    ).fetchone()
    if row is not None and row[0] != lead_id:
        raise ValueError(f"observation {observation_id} is not lead {lead_id}'s")
    if row is None or row[1] != "pending_review":
        raise ValueError(f"observation {observation_id} is not a pending_review observation")


def open_blocker(
    db: sqlite3.Connection,
    context: EventContext,
    lead_id: str,
    kind: BlockerKind,
    owner: BlockerOwner,
    detail: BlockerDetail,
) -> int:
    """Insert an open blocker, write `blocker_opened` and return the blocker id. The caller commits.

    Raises ValueError, writing nothing, for a blocker `refuse_unservable_blocker` refuses and for an
    observation item whose observation is not this lead's `pending_review` one.
    """
    refuse_unservable_blocker(kind, detail)
    if detail.item_kind == "observation":
        assert detail.observation_id is not None  # refuse_unservable_blocker requires it
        _require_pending_observation(db, lead_id, detail.observation_id)
    cursor = db.execute(
        "INSERT INTO blockers (lead_id, kind, owner, detail_json) VALUES (?, ?, ?, ?)",
        (lead_id, kind, owner, detail.model_dump_json()),
    )
    blocker_id = cursor.lastrowid
    assert blocker_id is not None  # an INSERT always sets it
    event_id = append_event(
        db,
        context,
        EventType.blocker_opened,
        BlockerOpened(blocker_id=blocker_id, kind=kind, owner=owner, detail=detail),
        lead_id=lead_id,
    )
    db.execute("UPDATE blockers SET opened_event_id = ? WHERE id = ?", (event_id, blocker_id))
    return blocker_id


def close_blocker(db: sqlite3.Connection, context: EventContext, blocker_id: int) -> None:
    """Write `blocker_closed` and record it on the blocker. The caller commits.

    Raises ValueError when the blocker does not exist or is already closed.
    """
    row = db.execute(
        "SELECT lead_id, kind, closed_event_id FROM blockers WHERE id = ?", (blocker_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"no blocker {blocker_id}")
    lead_id, kind, closed_event_id = row
    if closed_event_id is not None:
        raise ValueError(f"blocker {blocker_id} is already closed")
    event_id = append_event(
        db,
        context,
        EventType.blocker_closed,
        BlockerClosed(blocker_id=blocker_id, kind=kind),
        lead_id=lead_id,
    )
    db.execute("UPDATE blockers SET closed_event_id = ? WHERE id = ?", (event_id, blocker_id))


def open_blockers(db: sqlite3.Connection, lead_id: str) -> list[Blocker]:
    """The lead's open blockers, oldest first."""
    rows = db.execute(
        "SELECT id, lead_id, kind, owner, detail_json FROM blockers"
        " WHERE lead_id = ? AND closed_event_id IS NULL ORDER BY id",
        (lead_id,),
    ).fetchall()
    return [
        Blocker(
            id=row[0],
            lead_id=row[1],
            kind=row[2],
            owner=row[3],
            detail=BlockerDetail.model_validate_json(row[4]),
        )
        for row in rows
    ]


def primary_next_action(db: sqlite3.Connection, lead_id: str) -> Blocker | None:
    """The lead's highest-priority open blocker (7.1), the oldest of its kind; None for a terminal lead or one with no blocker."""
    row = db.execute("SELECT status FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    if row is None:
        raise ValueError(f"no lead {lead_id}")
    if row[0] in TERMINAL_STATUSES:
        return None
    blockers = open_blockers(db, lead_id)
    if not blockers:
        return None
    return min(blockers, key=lambda b: (BLOCKER_KINDS_BY_PRIORITY.index(b.kind), b.id))
