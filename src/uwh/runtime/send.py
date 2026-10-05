# ABOUTME: The send primitive of 7.5: drafts and their rounds, edit_draft, the dispatch that commits `dispatching` before the post, reconciliation of an ambiguous post, and the close of an intent that was not sent.
# ABOUTME: A post runs outside any transaction; each result is recorded in a transaction of its own, with an event context built after the post, so no event is dated before it.
import json
import sqlite3
import uuid
from dataclasses import dataclass, replace

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
    REQUEST_KINDS,
)
from uwh.runtime.events import EventContext, MakeContext, append_event, require_current_run
from uwh.runtime.hashing import payload_hash
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.policy import ApprovalBinding, autonomy_level, manifest_refusal
from uwh.runtime.waits import Blocker, close_blocker, open_blocker, open_blockers
from uwh.runtime.workflow import (
    lead_revision_and_plan_hash,
    transition,
    transition_refusal,
    unit_of_work,
)
from uwh.skills.manifest import SkillManifest
from uwh.skills.vertical import STATUS_AFTER_SEND

# A.8: the address every message is sent from.
SENDER = "uw@stand.com"


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
    values = list(row)
    values[8] = json.loads(values[8])  # the ask ids
    return Intent(*values)


def intent_in_state(db: sqlite3.Connection, intent_id: str, *states: IntentState) -> Intent:
    """The intent with that id, which must be in one of the states. Raises ValueError otherwise."""
    intent = read_intent(db, intent_id)
    if intent is None:
        raise ValueError(f"there is no intent {intent_id}")
    if intent.state not in states:
        raise ValueError(f"intent {intent_id} is {intent.state}, not {' or '.join(states)}")
    return intent


def _require_current_run(db: sqlite3.Connection, context: EventContext, intent: Intent) -> None:
    """Raise StaleRun unless both the run of the context and the run of the intent are current: the
    sender acts for the run that built its context, on the intents of that run."""
    require_current_run(db, context.run_id)
    require_current_run(db, intent.run_id)


def _class_of(kind: MessageKind) -> str:
    return f"send_{kind}"


# ---- drafts -------------------------------------------------------------------------------------


def _next_round(db: sqlite3.Connection, lead_id: str, kind: MessageKind) -> int:
    """Rounds number requests only: a request takes the round after the last one, and a quote packet
    or a decline notice carries the round of the last request, or 0 (7.5)."""
    placeholders = ", ".join("?" for _ in REQUEST_KINDS)
    (last,) = db.execute(
        f"SELECT COALESCE(MAX(round), 0) FROM intents WHERE lead_id = ?"
        f" AND kind IN ({placeholders}) AND state != 'closed_unsent'",
        (lead_id, *REQUEST_KINDS),
    ).fetchone()
    return int(last) + 1 if kind in REQUEST_KINDS else int(last)


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


def _open_draft_item(
    db: sqlite3.Connection, context: EventContext, intent: Intent, text: str | None = None
) -> None:
    """Open the `underwriter_review` item that holds the draft; `text` is the reason it shows."""
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
            text=text or f"Review this {intent.kind} before it is sent.",
        ),
    )


def _insert_draft(
    db: sqlite3.Connection, context: EventContext, intent: Intent, *, waits_for_approval: bool
) -> str:
    """Insert the intent, which is in state `draft`, with its `intent_created` event, and open the
    item that holds it when it waits for approval. Returns the intent id."""
    db.execute(
        f"INSERT INTO intents ({_INTENT_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            intent.id,
            intent.run_id,
            intent.lead_id,
            intent.round,
            intent.kind,
            intent.recipient,
            intent.subject,
            intent.body,
            json.dumps(intent.ask_ids),
            intent.payload_hash,
            intent.state,
            intent.mailbox_id,
        ),
    )
    append_event(
        db,
        context,
        EventType.intent_created,
        IntentCreated(
            intent_id=intent.id,
            round=intent.round,
            kind=intent.kind,
            recipient=intent.recipient,
            subject=intent.subject,
            body=intent.body,
            ask_ids=intent.ask_ids,
            payload_hash=intent.payload_hash,
        ),
        lead_id=intent.lead_id,
    )
    if waits_for_approval:
        _open_draft_item(db, context, intent)
    return intent.id


def create_draft(
    db: sqlite3.Connection,
    context: EventContext,
    manifest: SkillManifest,
    lead_id: str,
    kind: MessageKind,
    recipient: str,
    subject: str,
    body: str,
    ask_ids: list[str],
) -> str:
    """Insert an intent in state `draft`, write `intent_created` and return the intent id.

    `manifest` is the issuing skill's; it must declare the send class of the kind (8). A draft whose
    class does not run at `auto` waits as an `underwriter_review` item that names it. Sends nothing;
    the caller commits. Raises ValueError, writing nothing, for a class the manifest does not declare.
    """
    refusal = manifest_refusal(manifest, _class_of(kind))
    if refusal is not None:
        raise ValueError(refusal)
    intent = Intent(
        uuid.uuid4().hex,
        context.run_id,
        lead_id,
        _next_round(db, lead_id, kind),
        kind,
        recipient,
        subject,
        body,
        ask_ids,
        payload_hash(recipient, subject, body),
        "draft",
        None,
    )
    return _insert_draft(
        db, context, intent, waits_for_approval=autonomy_level(_class_of(kind)) != "auto"
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
    with the kind after the edit; return that event's id (7.5). A `routine_request` becomes a
    `sensitive_request`, so it waits for approval; a quote packet or decline notice keeps its kind.
    Raises ValueError for an intent that is not a draft. The caller commits.
    """
    intent = intent_in_state(db, intent_id, "draft")
    kind: MessageKind = "sensitive_request" if intent.kind == "routine_request" else intent.kind
    hashed = payload_hash(intent.recipient, subject, body)
    edited = replace(intent, subject=subject, body=body, payload_hash=hashed, kind=kind)
    db.execute(
        "UPDATE intents SET subject = ?, body = ?, payload_hash = ?, kind = ? WHERE id = ?",
        (subject, body, hashed, kind, intent_id),
    )
    void_approvals(db, intent_id)
    revision, _ = lead_revision_and_plan_hash(db, intent.lead_id)
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
    if autonomy_level(_class_of(kind)) != "auto" and _draft_item(db, edited) is None:
        _open_draft_item(db, context, edited)
    return event_id


# ---- dispatch -----------------------------------------------------------------------------------


def _current_binding(db: sqlite3.Connection, intent: Intent, ruleset_hash: str) -> ApprovalBinding:
    revision, plan_hash = lead_revision_and_plan_hash(db, intent.lead_id)
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


def _return_to_review(
    db: sqlite3.Connection,
    context: EventContext,
    intent: Intent,
    item: Blocker | None,
    reason: str | None = None,
) -> None:
    """Void the approvals of the draft and leave it with an open item. With a `reason` the item shows
    it, replacing an item that shows another; without one an open item stays as it is."""
    void_approvals(db, intent.id)
    if item is not None and reason is not None:
        close_blocker(db, context, item.id)
        item = None
    if item is None:
        _open_draft_item(db, context, intent, reason)


def _begin_dispatch(
    db: sqlite3.Connection, make_context: MakeContext, intent_id: str
) -> Intent | None:
    """Commit the state `dispatching` in its own transaction and return the intent, or return None when
    the draft is not sent now: it is not a draft, it waits for an approval, it returns to review, or
    another intent of its lead is in flight.

    The rechecks and the move to `dispatching` share one transaction that holds the write lock, so
    two senders cannot both pass them: a lead has at most one intent `dispatching` (7.5, one sender
    per lead).
    """
    with unit_of_work(db):
        context = make_context()
        intent = read_intent(db, intent_id)
        if intent is None or intent.state != "draft":
            return None
        _require_current_run(db, context, intent)
        item = _draft_item(db, intent)
        if autonomy_level(_class_of(intent.kind)) == "review" or item is not None:
            approved = _approved_binding(db, intent_id)
            if approved is None:
                if item is None:
                    _open_draft_item(db, context, intent)
                return None
            if approved != _current_binding(db, intent, context.ruleset_hash):
                _return_to_review(db, context, intent, item)
                return None
        target = STATUS_AFTER_SEND.get(intent.kind)
        refusal = None if target is None else transition_refusal(db, intent.lead_id, target)
        if refusal is not None:
            _return_to_review(db, context, intent, item, refusal)
            return None
        if db.execute(
            "SELECT 1 FROM intents WHERE lead_id = ? AND state = 'dispatching'", (intent.lead_id,)
        ).fetchone():
            return None
        db.execute("UPDATE intents SET state = 'dispatching' WHERE id = ?", (intent_id,))
        if item is not None:
            close_blocker(db, context, item.id)
        return intent


def _post(mailbox: MailboxClient, intent: Intent) -> int | None:
    """Post the intent and return the mailbox id of the message, or None when the result is ambiguous:
    the request failed in transport or the mailbox answered with an error status (7.5 step 4)."""
    metadata = {
        "intent_id": intent.id,
        "run_id": intent.run_id,
        "kind": intent.kind,
        "round": intent.round,
        "payload_hash": intent.payload_hash,
    }
    try:
        posted = mailbox.send(
            intent.lead_id, intent.recipient, SENDER, intent.subject, intent.body, metadata
        )
    except httpx2.HTTPError:
        return None
    return int(posted["id"])


def dispatch(
    db: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext, intent_id: str
) -> None:
    """Send a draft if its class and approval allow it now (7.4, 7.5).

    Commits `dispatching`, posts outside any transaction, then records `sent`; an ambiguous result is
    reconciled by the intent id. A draft that needs an approval it does not have waits as an item; one
    whose approval does not hold against the current values, or whose packet or notice the lead's
    status does not allow, returns to review and loses the approval; another intent of the lead in
    flight leaves the draft for a later pass. `make_context` builds the context of each event when it
    is written. Raises RuntimeError inside a transaction.
    Raises StaleRun when the run of the draft or the run of the context has been replaced, before the
    post or after it; nothing is written then (14).
    """
    if db.in_transaction:
        raise RuntimeError(
            "a dispatch commits and posts on its own, so the connection must not be in a transaction"
        )
    begun = _begin_dispatch(db, make_context, intent_id)
    if begun is None:
        return
    mailbox_id = _post(mailbox, begun)
    if mailbox_id is None:
        reconcile(db, mailbox, make_context, intent_id)
    else:
        _record_sent(db, mailbox, make_context, begun, mailbox_id)


def dispatch_ready(
    db: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext, lead_id: str
) -> None:
    """Dispatch every draft the lead holds when the pass starts, in the order they were created. A
    draft that has left `draft` by then is skipped."""
    for (intent_id,) in db.execute(
        "SELECT id FROM intents WHERE lead_id = ? AND state = 'draft' ORDER BY rowid", (lead_id,)
    ).fetchall():
        dispatch(db, mailbox, make_context, intent_id)


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
    request opens its round, a packet or a notice moves the lead (A.2, A.3). A sent message is history
    (7.3): where the lead's status does not allow the move, the status stays. An intent that is not
    `dispatching` or `unknown`, because another command settled it first, is left as it is.
    """
    with unit_of_work(db):
        context = make_context()
        _require_current_run(db, context, intent)
        _record_faults(db, context, mailbox, intent.lead_id)
        settled = db.execute(
            "UPDATE intents SET state = 'sent', mailbox_id = ?"
            " WHERE id = ? AND state IN ('dispatching', 'unknown')",
            (mailbox_id, intent.id),
        )
        if settled.rowcount == 0:
            return
        append_event(
            db,
            context,
            EventType.message_sent,
            MessageSent(intent_id=intent.id, mailbox_id=mailbox_id),
            lead_id=intent.lead_id,
        )
        _close_delivery_unknown(db, context, intent)
        if intent.kind in REQUEST_KINDS:
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
            target = STATUS_AFTER_SEND[intent.kind]
            if transition_refusal(db, intent.lead_id, target) is None:
                transition(db, intent.lead_id, target)


def _record_unknown(
    db: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext, intent: Intent
) -> None:
    """Set `unknown`, write `delivery_unknown` and open the underwriter's blocker. An intent that is not
    `dispatching`, because it is `unknown` with both already or another command settled it, is left
    as it is."""
    with unit_of_work(db):
        context = make_context()
        _require_current_run(db, context, intent)
        _record_faults(db, context, mailbox, intent.lead_id)
        settled = db.execute(
            "UPDATE intents SET state = 'unknown' WHERE id = ? AND state = 'dispatching'",
            (intent.id,),
        )
        if settled.rowcount == 0:
            return
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
                text="The mailbox did not show a message for this intent, so it may not have been delivered.",
            ),
        )


def reconcile(
    db: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext, intent_id: str
) -> None:
    """Settle an intent in `dispatching` or `unknown` by listing the lead's mailbox and matching the
    intent id (7.5 step 4). A match is recorded as `sent`; no match leaves it `unknown`, with
    `delivery_unknown` written and its blocker opened when it was `dispatching`.

    A listing that fails finds no match, so the intent is `unknown` and nothing is sent again.
    Raises RuntimeError inside a transaction, ValueError for an intent in another state and
    StaleRun, writing nothing, for an intent of a replaced run.
    """
    if db.in_transaction:
        raise RuntimeError("a reconciliation lists the mailbox outside any transaction")
    intent = intent_in_state(db, intent_id, "dispatching", "unknown")
    try:
        listed = mailbox.list_for_lead(intent.lead_id)
    except httpx2.HTTPError:
        listed = []
    matches = [m for m in listed if (m["metadata"] or {}).get("intent_id") == intent.id]
    if matches:
        _record_sent(db, mailbox, make_context, intent, matches[0]["id"])
    else:
        _record_unknown(db, mailbox, make_context, intent)


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
    kind and text that waits for approval whatever its class (7.5). The workflow creates the draft.
    The caller commits. Raises ValueError for an intent that is not `unknown`.
    """
    intent = intent_in_state(db, intent_id, "unknown")
    db.execute("UPDATE intents SET state = 'closed_unsent' WHERE id = ?", (intent_id,))
    _close_delivery_unknown(db, context, intent)
    fresh = replace(
        intent, id=uuid.uuid4().hex, run_id=context.run_id, state="draft", mailbox_id=None
    )
    return _insert_draft(db, replace(context, actor="workflow"), fresh, waits_for_approval=True)
