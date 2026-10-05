# ABOUTME: The waiting primitive of 7.1: a blocker row with a kind, an owner and a resume trigger; opens and closes blockers, lists a lead's open ones and names its primary next action.
# ABOUTME: Opening refuses the blockers `BlockerView` and `QuestionItem` refuse, and the ones whose observation is another lead's or whose choice ids sit on the wrong kind, so a bad write fails at the write; every change writes its event and the caller commits.
import sqlite3
from dataclasses import dataclass

from uwh.runtime.event_types import (
    ApprovalItemKind,
    BlockerClosed,
    BlockerDetail,
    BlockerKind,
    BlockerOpened,
    BlockerOwner,
    EventType,
    ReviewCause,
)
from uwh.runtime.events import EventContext, append_event
from uwh.skills.vertical import (
    BLOCKER_KINDS_BY_PRIORITY,
    PERSISTING_REVIEW_CAUSES,
    TERMINAL_STATUSES,
)

# The item kinds an underwriter_review blocker takes (A.11).
_REVIEW_ITEM_KINDS: tuple[ApprovalItemKind, ...] = (
    "draft",
    "observation",
    "no_contact_route",
    "review",
)

# 7.4: a dispatch the stop or a class set to `off` refused leaves its draft in review.
_HELD_DRAFT_CAUSES: tuple[ReviewCause, ...] = ("draft_held_by_stop", "draft_held_class_off")


@dataclass(frozen=True)
class Blocker:
    id: int
    lead_id: str
    kind: BlockerKind
    owner: BlockerOwner
    detail: BlockerDetail


def _refuse_unservable(
    db: sqlite3.Connection, lead_id: str, kind: BlockerKind, detail: BlockerDetail
) -> None:
    """Raise ValueError for a blocker `BlockerView` or `QuestionItem` would refuse, for an observation
    item naming another lead's observation, and for choice ids on a blocker that is not a question."""
    item_kind = detail.item_kind
    if kind == "underwriter_review":
        if item_kind not in _REVIEW_ITEM_KINDS:
            raise ValueError(f"an underwriter_review item_kind is one of {_REVIEW_ITEM_KINDS}")
    elif kind == "delivery_unknown":
        if item_kind != "delivery_unknown":
            raise ValueError("a delivery_unknown blocker has the item_kind delivery_unknown")
    elif item_kind is not None:
        raise ValueError(f"a {kind} blocker has no item_kind")
    if item_kind == "draft" and detail.intent_id is None:
        raise ValueError("a draft review names its draft: intent_id")
    if detail.cause_persists and item_kind != "review":
        raise ValueError("only a review holds a persistent cause")
    if item_kind == "review":
        if detail.cause is None:
            raise ValueError("a review has a cause")
        persists = detail.cause in PERSISTING_REVIEW_CAUSES
        if detail.cause_persists != persists:
            raise ValueError(f"cause_persists is {persists} for {detail.cause}")
    elif detail.cause is not None:
        raise ValueError("only a review has a cause")
    if detail.cause in _HELD_DRAFT_CAUSES and detail.intent_id is None:
        raise ValueError("a held draft's review names its draft: intent_id")
    if kind == "underwriter_question" and not detail.choice_ids:
        raise ValueError("a question blocker names its choices: choice_ids")
    if kind != "underwriter_question" and detail.choice_ids:
        raise ValueError(f"a {kind} blocker has no choice_ids")
    if item_kind == "observation":
        _require_pending_observation(db, lead_id, detail.observation_id)


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

    Raises ValueError, writing nothing, for a blocker the lead detail view would refuse, for an
    observation item naming another lead's observation and for choice ids on a non-question blocker.
    """
    _refuse_unservable(db, lead_id, kind, detail)
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
