# ABOUTME: The send primitive of 7.5: drafts and their rounds, edit_draft, the dispatch that commits `dispatching` before the post, reconciliation of an ambiguous post, and the close of an intent that was not sent.
# ABOUTME: A post runs outside any transaction; each result is recorded in a transaction of its own, with an event context built after the post, so no event is dated before it.
import json
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, get_args

import httpx2

from uwh.runtime.event_types import (
    BlockerDetail,
    DeliveryUnknown,
    DraftEdited,
    EventType,
    FaultInjected,
    IntentCreated,
    IntentState,
    MessageKind,
    MessageSent,
    RequestKind,
    Status,
)
from uwh.runtime.events import EventContext, append_event
from uwh.runtime.hashing import payload_hash
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.policy import ApprovalBinding, autonomy_level, binding_changes
from uwh.runtime.waits import Blocker, close_blocker, open_blocker, open_blockers
from uwh.runtime.workflow import transition, unit_of_work
from uwh.skills.vertical import TRANSITIONS

# A.8: the address every message is sent from.
SENDER = "uw@stand.com"

MakeContext = Callable[[], EventContext]
DispatchOutcome = Literal[
    "sent",
    "unknown",
    "waiting_for_approval",
    "returned_to_review",
    "lead_busy",
    "not_a_draft",
]

_REQUEST_KINDS: tuple[str, ...] = get_args(RequestKind)
# The status a lead takes when a packet or a notice is sent (A.3).
_STATUS_AFTER_SEND: dict[str, Status] = {"quote_packet": "quote_sent", "decline_notice": "declined"}


@dataclass(frozen=True)
class Intent:
    """One row of `intents` (A.1)."""

    id: str
    run_id: str
    lead_id: str
    round: int
    kind: MessageKind
    recipient: str
    subject: str
    body: str
    ask_ids: list[str]
    payload_hash: str
    state: IntentState
    mailbox_id: int | None


_INTENT_COLUMNS = (
    "id, run_id, lead_id, round, kind, recipient, subject, body, ask_ids_json, payload_hash,"
    " state, mailbox_id"
)


def read_intent(db: sqlite3.Connection, intent_id: str) -> Intent | None:
    """The intent with that id, or None."""
    row = db.execute(f"SELECT {_INTENT_COLUMNS} FROM intents WHERE id = ?", (intent_id,)).fetchone()
    if row is None:
        return None
    (
        id_,
        run_id,
        lead_id,
        round_,
        kind,
        recipient,
        subject,
        body,
        ask_ids,
        hashed,
        state,
        mailbox_id,
    ) = row
    return Intent(
        id_,
        run_id,
        lead_id,
        round_,
        kind,
        recipient,
        subject,
        body,
        json.loads(ask_ids),
        hashed,
        state,
        mailbox_id,
    )


def _draft(db: sqlite3.Connection, intent_id: str) -> Intent:
    intent = read_intent(db, intent_id)
    if intent is None:
        raise ValueError(f"there is no intent {intent_id}")
    if intent.state != "draft":
        raise ValueError(f"intent {intent_id} is {intent.state}, not a draft")
    return intent


def _class_of(kind: MessageKind) -> str:
    return f"send_{kind}"


# ---- drafts -------------------------------------------------------------------------------------


def _next_round(db: sqlite3.Connection, lead_id: str, kind: MessageKind) -> int:
    """Rounds number requests only: a request takes the round after the last one, and a quote packet
    or a decline notice carries the round of the last request, or 0 (7.5)."""
    placeholders = ", ".join("?" for _ in _REQUEST_KINDS)
    (last,) = db.execute(
        f"SELECT COALESCE(MAX(round), 0) FROM intents WHERE lead_id = ?"
        f" AND kind IN ({placeholders}) AND state != 'closed_unsent'",
        (lead_id, *_REQUEST_KINDS),
    ).fetchone()
    return int(last) + 1 if kind in _REQUEST_KINDS else int(last)


def _draft_item(db: sqlite3.Connection, intent: Intent) -> Blocker | None:
    """The open `underwriter_review` item that reviews this draft, if there is one."""
    for blocker in open_blockers(db, intent.lead_id):
        if (
            blocker.kind == "underwriter_review"
            and blocker.detail.item_kind == "draft"
            and blocker.detail.intent_id == intent.id
        ):
            return blocker
    return None


def _open_draft_item(db: sqlite3.Connection, context: EventContext, intent: Intent) -> None:
    open_blocker(
        db,
        context,
        intent.lead_id,
        "underwriter_review",
        "underwriter",
        BlockerDetail(
            item_kind="draft",
            intent_id=intent.id,
            resume_trigger="an underwriter approves the draft",
            text=f"Review this {intent.kind} before it is sent.",
        ),
    )


def _insert_draft(
    db: sqlite3.Connection,
    context: EventContext,
    lead_id: str,
    round_: int,
    kind: MessageKind,
    recipient: str,
    subject: str,
    body: str,
    ask_ids: list[str],
    *,
    waits_for_approval: bool,
) -> str:
    intent_id = uuid.uuid4().hex
    hashed = payload_hash(recipient, subject, body)
    db.execute(
        f"INSERT INTO intents ({_INTENT_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', NULL)",
        (
            intent_id,
            context.run_id,
            lead_id,
            round_,
            kind,
            recipient,
            subject,
            body,
            json.dumps(ask_ids),
            hashed,
        ),
    )
    append_event(
        db,
        context,
        EventType.intent_created,
        IntentCreated(
            intent_id=intent_id,
            round=round_,
            kind=kind,
            recipient=recipient,
            subject=subject,
            body=body,
            ask_ids=ask_ids,
            payload_hash=hashed,
        ),
        lead_id=lead_id,
    )
    if waits_for_approval:
        intent = read_intent(db, intent_id)
        assert intent is not None  # inserted above
        _open_draft_item(db, context, intent)
    return intent_id


def create_draft(
    db: sqlite3.Connection,
    context: EventContext,
    lead_id: str,
    kind: MessageKind,
    recipient: str,
    subject: str,
    body: str,
    ask_ids: list[str],
) -> str:
    """Insert an intent in state `draft`, write `intent_created` and return the intent id.

    A draft whose class does not run at `auto` waits as an `underwriter_review` item that names it.
    Sends nothing; the caller commits.
    """
    return _insert_draft(
        db,
        context,
        lead_id,
        _next_round(db, lead_id, kind),
        kind,
        recipient,
        subject,
        body,
        ask_ids,
        waits_for_approval=autonomy_level(db, _class_of(kind)) != "auto",
    )


def void_approvals(db: sqlite3.Connection, intent_id: str) -> None:
    """Remove the approvals of a draft. The `approval_recorded` events keep the record."""
    db.execute("DELETE FROM approvals WHERE intent_id = ? AND decision = 'approved'", (intent_id,))


def edit_draft(
    db: sqlite3.Connection,
    context: EventContext,
    intent_id: str,
    subject: str,
    body: str,
    reason: str,
) -> int:
    """Replace the subject, body and payload hash of a draft, void its approval and write `draft_edited`
    with the kind it now has; return that event's id (7.5). A `routine_request` becomes a
    `sensitive_request`, so it waits for approval; a quote packet or decline notice keeps its kind.
    Raises ValueError for an intent that is not a draft. The caller commits.
    """
    intent = _draft(db, intent_id)
    kind: MessageKind = "sensitive_request" if intent.kind == "routine_request" else intent.kind
    hashed = payload_hash(intent.recipient, subject, body)
    db.execute(
        "UPDATE intents SET subject = ?, body = ?, payload_hash = ?, kind = ? WHERE id = ?",
        (subject, body, hashed, kind, intent_id),
    )
    void_approvals(db, intent_id)
    (revision,) = db.execute(
        "SELECT revision FROM leads WHERE lead_id = ?", (intent.lead_id,)
    ).fetchone()
    event_id = append_event(
        db,
        context,
        EventType.draft_edited,
        DraftEdited(
            intent_id=intent_id,
            kind=kind,
            subject=subject,
            body=body,
            payload_hash=hashed,
            reason=reason,
            lead_revision=revision,
        ),
        lead_id=intent.lead_id,
    )
    edited = read_intent(db, intent_id)
    assert edited is not None  # updated above
    if autonomy_level(db, _class_of(kind)) != "auto" and _draft_item(db, edited) is None:
        _open_draft_item(db, context, edited)
    return event_id


# ---- dispatch -----------------------------------------------------------------------------------


def _current_binding(db: sqlite3.Connection, intent: Intent, ruleset_hash: str) -> ApprovalBinding:
    revision, plan_hash = db.execute(
        "SELECT revision, plan_hash FROM leads WHERE lead_id = ?", (intent.lead_id,)
    ).fetchone()
    # A lead with no plan has no hash an approval can match, so the empty text never equals one.
    return ApprovalBinding(
        revision, plan_hash or "", ruleset_hash, intent.recipient, intent.payload_hash
    )


def _approved_binding(db: sqlite3.Connection, intent_id: str) -> ApprovalBinding | None:
    """The values the latest live approval of the draft is bound to, or None when it has none."""
    row = db.execute(
        "SELECT lead_revision, plan_hash, ruleset_hash, recipient, payload_hash FROM approvals"
        " WHERE intent_id = ? AND decision = 'approved' ORDER BY id DESC LIMIT 1",
        (intent_id,),
    ).fetchone()
    return None if row is None else ApprovalBinding(*row)


def _refuse_what_tier_one_holds(db: sqlite3.Connection, intent: Intent) -> None:
    """A dispatch the emergency stop or a class set to `off` refuses leaves the draft held in review
    with the reason (7.4); that hold is not built."""
    if autonomy_level(db, _class_of(intent.kind)) == "off":
        raise NotImplementedError("holding a draft whose class is off")
    row = db.execute("SELECT value_json FROM settings WHERE key = 'emergency_stop'").fetchone()
    if row is not None and json.loads(row[0]) is True:
        raise NotImplementedError("holding a draft while the emergency stop is engaged")


def _begin_dispatch(
    db: sqlite3.Connection, make_context: MakeContext, intent_id: str
) -> Intent | DispatchOutcome:
    """Commit the state `dispatching` in its own transaction, or return why the draft is not sent now.

    The rechecks and the move to `dispatching` share one transaction that holds the write lock, so
    two senders cannot both pass them: a lead has at most one intent `dispatching` (7.5, one sender
    per lead).
    """
    with unit_of_work(db):
        context = make_context()
        intent = read_intent(db, intent_id)
        if intent is None or intent.state != "draft":
            return "not_a_draft"
        _refuse_what_tier_one_holds(db, intent)
        item = _draft_item(db, intent)
        if autonomy_level(db, _class_of(intent.kind)) == "review" or item is not None:
            approved = _approved_binding(db, intent_id)
            if approved is None:
                return "waiting_for_approval"
            if binding_changes(approved, _current_binding(db, intent, context.ruleset_hash)):
                void_approvals(db, intent_id)
                if item is None:
                    _open_draft_item(db, context, intent)
                return "returned_to_review"
        target = _STATUS_AFTER_SEND.get(intent.kind)
        (status,) = db.execute(
            "SELECT status FROM leads WHERE lead_id = ?", (intent.lead_id,)
        ).fetchone()
        if target is not None and (status, target) not in TRANSITIONS:
            raise ValueError(f"a lead cannot move from {status} to {target}")
        if db.execute(
            "SELECT 1 FROM intents WHERE lead_id = ? AND state = 'dispatching'", (intent.lead_id,)
        ).fetchone():
            return "lead_busy"
        db.execute("UPDATE intents SET state = 'dispatching' WHERE id = ?", (intent_id,))
        if item is not None:
            close_blocker(db, context, item.id)
        return intent


def dispatch(
    db: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext, intent_id: str
) -> DispatchOutcome:
    """Send a draft if its class and approval allow it now (7.4, 7.5).

    Commits `dispatching`, posts outside any transaction, then records `sent`; an ambiguous result is
    reconciled by the intent id. A draft that needs an approval it does not have waits; one whose
    approval does not hold against the current values returns to review and loses the approval; another intent of the lead in
    flight leaves the draft for a later pass. `make_context` builds the context of each event when it is
    written. Raises RuntimeError inside a transaction, ValueError when a lead's status does not allow the
    move a packet or notice makes, and NotImplementedError where a hold is not built.
    """
    if db.in_transaction:
        raise RuntimeError(
            "a dispatch commits and posts on its own, so the connection must not be in a transaction"
        )
    begun = _begin_dispatch(db, make_context, intent_id)
    if not isinstance(begun, Intent):
        return begun
    metadata = {
        "intent_id": begun.id,
        "run_id": begun.run_id,
        "kind": begun.kind,
        "round": begun.round,
        "payload_hash": begun.payload_hash,
    }
    try:
        posted = mailbox.send(
            begun.lead_id, begun.recipient, SENDER, begun.subject, begun.body, metadata
        )
    except httpx2.HTTPError:
        return reconcile(db, mailbox, make_context, intent_id)
    _record_sent(db, mailbox, make_context, begun, posted["id"])
    return "sent"


def dispatch_ready(
    db: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext, lead_id: str
) -> None:
    """Dispatch every draft of the lead that can go now. A draft skipped because another sender held
    the lead is tried again once this pass has finished its own sends."""
    tried: set[str] = set()
    while True:
        waiting = [
            intent_id
            for (intent_id,) in db.execute(
                "SELECT id FROM intents WHERE lead_id = ? AND state = 'draft' ORDER BY rowid",
                (lead_id,),
            )
            if intent_id not in tried
        ]
        if not waiting:
            return
        tried.add(waiting[0])
        dispatch(db, mailbox, make_context, waiting[0])


# ---- results ------------------------------------------------------------------------------------


def _record_faults(
    db: sqlite3.Connection, context: EventContext, mailbox: MailboxClient, lead_id: str
) -> None:
    if mailbox.faults is None:
        return
    for fault in mailbox.faults.take_injected():
        append_event(
            db, context, EventType.fault_injected, FaultInjected(fault=fault), lead_id=lead_id
        )


def _close_delivery_unknown(db: sqlite3.Connection, context: EventContext, intent: Intent) -> None:
    for blocker in open_blockers(db, intent.lead_id):
        if blocker.kind == "delivery_unknown" and blocker.detail.intent_id == intent.id:
            close_blocker(db, context, blocker.id)


def _record_sent(
    db: sqlite3.Connection,
    mailbox: MailboxClient,
    make_context: MakeContext,
    intent: Intent,
    mailbox_id: int,
) -> None:
    """Record the mailbox id, set `sent`, write `message_sent`, and apply what a sent message does: a
    request opens its round, a packet or a notice moves the lead (A.2, A.3)."""
    with unit_of_work(db):
        context = make_context()
        _record_faults(db, context, mailbox, intent.lead_id)
        db.execute(
            "UPDATE intents SET state = 'sent', mailbox_id = ? WHERE id = ?",
            (mailbox_id, intent.id),
        )
        append_event(
            db,
            context,
            EventType.message_sent,
            MessageSent(intent_id=intent.id, mailbox_id=mailbox_id),
            lead_id=intent.lead_id,
        )
        _close_delivery_unknown(db, context, intent)
        if intent.kind in _REQUEST_KINDS:
            open_blocker(
                db,
                context,
                intent.lead_id,
                "producer_reply",
                "producer",
                BlockerDetail(
                    resume_trigger="the producer replies",
                    intent_id=intent.id,
                    text=f"Waiting for the producer's reply to round {intent.round}.",
                ),
            )
        else:
            transition(db, intent.lead_id, _STATUS_AFTER_SEND[intent.kind])


def _record_unknown(
    db: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext, intent: Intent
) -> None:
    """Set `unknown`, write `delivery_unknown` and open the underwriter's blocker; an intent already
    `unknown` has both."""
    with unit_of_work(db):
        context = make_context()
        _record_faults(db, context, mailbox, intent.lead_id)
        if intent.state == "unknown":
            return
        db.execute("UPDATE intents SET state = 'unknown' WHERE id = ?", (intent.id,))
        append_event(
            db,
            context,
            EventType.delivery_unknown,
            DeliveryUnknown(intent_id=intent.id),
            lead_id=intent.lead_id,
        )
        open_blocker(
            db,
            context,
            intent.lead_id,
            "delivery_unknown",
            "underwriter",
            BlockerDetail(
                item_kind="delivery_unknown",
                resume_trigger="an underwriter checks the mailbox",
                intent_id=intent.id,
                text="The mailbox shows no message for this intent, so it may not have been delivered.",
            ),
        )


def reconcile(
    db: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext, intent_id: str
) -> Literal["sent", "unknown"]:
    """Settle an intent in `dispatching` or `unknown` by listing the lead's mailbox and matching the
    intent id (7.5 step 4). A match is recorded as `sent`; no match leaves it `unknown`, with
    `delivery_unknown` written and its blocker opened when it was `dispatching`.

    A listing that fails raises and leaves the intent as it was. Raises RuntimeError inside a
    transaction and ValueError for an intent in another state.
    """
    if db.in_transaction:
        raise RuntimeError("a reconciliation lists the mailbox outside any transaction")
    intent = read_intent(db, intent_id)
    if intent is None:
        raise ValueError(f"there is no intent {intent_id}")
    if intent.state not in ("dispatching", "unknown"):
        raise ValueError(f"intent {intent_id} is {intent.state}, not dispatching or unknown")
    matches = [
        m
        for m in mailbox.list_for_lead(intent.lead_id)
        if (m["metadata"] or {}).get("intent_id") == intent.id
    ]
    if matches:
        _record_sent(db, mailbox, make_context, intent, matches[0]["id"])
        return "sent"
    _record_unknown(db, mailbox, make_context, intent)
    return "unknown"


def reconcile_dispatching(
    db: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext
) -> None:
    """Startup (7.5 step 5): reconcile every intent in `dispatching`, before any dispatch. Drafts are
    left alone."""
    for (intent_id,) in db.execute(
        "SELECT id FROM intents WHERE state = 'dispatching' ORDER BY rowid"
    ).fetchall():
        reconcile(db, mailbox, make_context, intent_id)


def close_unsent(db: sqlite3.Connection, context: EventContext, intent_id: str) -> str:
    """Close an `unknown` intent as not sent and return the id of a fresh draft of the same round,
    kind and text that waits for approval whatever its class (7.5). The caller commits.
    Raises ValueError for an intent that is not `unknown`.
    """
    intent = read_intent(db, intent_id)
    if intent is None:
        raise ValueError(f"there is no intent {intent_id}")
    if intent.state != "unknown":
        raise ValueError(f"intent {intent_id} is {intent.state}, not unknown")
    db.execute("UPDATE intents SET state = 'closed_unsent' WHERE id = ?", (intent_id,))
    _close_delivery_unknown(db, context, intent)
    return _insert_draft(
        db,
        context,
        intent.lead_id,
        intent.round,
        intent.kind,
        intent.recipient,
        intent.subject,
        intent.body,
        intent.ask_ids,
        waits_for_approval=True,
    )
