# ABOUTME: Tests the send primitive of 7.5 against Stand's mailbox in process: drafts and their rounds, edit_draft, the dispatch that commits `dispatching` before the post, one sender per lead, reconciliation, and the resolution of `delivery_unknown`.
# ABOUTME: Each test opens a real database, posts to the real mailbox app and reads the mailbox and the event log back; a lead and a message are keyed by lead id and intent id, never the mailbox row id.
import json
import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, get_args

import httpx2
import pytest

from tests.runtime.helpers import (
    ASKER,
    PLAN_HASH,
    RECIPIENT,
    REVISION,
    RULESET,
    MakeContext,
    command_environment,
    draft_and_dispatch,
    events_of,
    insert_dispatching,
    skill_manifest,
    state_of,
)
from tests.runtime.helpers import LEAD_ID as LEAD
from uwh.runtime.commands import submit_command
from uwh.runtime.event_types import DraftEdited, EventType, IntentCreated, MessageSent, RequestKind
from uwh.runtime.events import EventContext, StaleRun, read_events
from uwh.runtime.faults import FaultPlan
from uwh.runtime.hashing import payload_hash
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.runs import RunEnvironment
from uwh.runtime.send import (
    _record_sent,
    create_draft,
    dispatch,
    dispatch_ready,
    edit_draft,
    read_intent,
    reconcile,
    reconcile_dispatching,
    replace_stale_drafts,
)
from uwh.runtime.store import open_store
from uwh.runtime.waits import Blocker, open_blockers
from uwh.runtime.workflow import Step


def draft(db: sqlite3.Connection, context: MakeContext, kind: str = "routine_request") -> str:
    intent_id = create_draft(
        db,
        context(),
        ASKER,
        LEAD,
        kind,
        RECIPIENT,
        "Subject",
        "Body",
        ["acreage"],  # type: ignore[arg-type]
    )
    db.commit()
    return intent_id


def intent_row(db: sqlite3.Connection, intent_id: str) -> dict[str, Any]:
    cursor = db.execute("SELECT * FROM intents WHERE id = ?", (intent_id,))
    names = [column[0] for column in cursor.description]
    return dict(zip(names, cursor.fetchone(), strict=True))


def messages(mailbox: MailboxClient) -> list[dict[str, Any]]:
    # The mailbox lists newest first.
    return sorted(mailbox.list_for_lead(LEAD), key=lambda m: m["id"])


def message_intents(mailbox: MailboxClient) -> list[str]:
    return [m["metadata"]["intent_id"] for m in messages(mailbox)]


def draft_items(db: sqlite3.Connection, intent_id: str) -> list[Blocker]:
    return [
        b
        for b in open_blockers(db, LEAD)
        if b.kind == "underwriter_review"
        and b.detail.item_kind == "draft"
        and b.detail.intent_id == intent_id
    ]


def approve_row(db: sqlite3.Connection, intent_id: str, **overrides: Any) -> None:
    """An approval of the draft bound to the values the lead and the draft hold now, with any
    of the five replaced."""
    intent = intent_row(db, intent_id)
    bound: dict[str, Any] = {
        "lead_revision": REVISION,
        "plan_hash": PLAN_HASH,
        "ruleset_hash": RULESET,
        "recipient": intent["recipient"],
        "payload_hash": intent["payload_hash"],
        **overrides,
    }
    db.execute(
        "INSERT INTO approvals (lead_id, item_kind, intent_id, lead_revision, plan_hash,"
        " ruleset_hash, recipient, payload_hash, actor, decision, reason, event_id)"
        " VALUES (?, 'draft', ?, ?, ?, ?, ?, ?, 'underwriter', 'approved', 'ok', NULL)",
        (
            LEAD,
            intent_id,
            bound["lead_revision"],
            bound["plan_hash"],
            bound["ruleset_hash"],
            bound["recipient"],
            bound["payload_hash"],
        ),
    )
    db.commit()


def approved_rows(db: sqlite3.Connection, intent_id: str) -> int:
    (count,) = db.execute(
        "SELECT COUNT(*) FROM approvals WHERE intent_id = ? AND decision = 'approved'",
        (intent_id,),
    ).fetchone()
    return int(count)


def duplicates(mailbox: MailboxClient) -> list[tuple[Any, ...]]:
    """The keys of a duplicate (7.5): more than one request for one (run id, lead id, round), or
    more than one quote packet or decline notice for one (run id, lead id)."""
    requests = get_args(RequestKind)
    keys = [
        (m["metadata"]["run_id"], LEAD, m["metadata"]["round"])
        if m["metadata"]["kind"] in requests
        else (m["metadata"]["run_id"], LEAD, m["metadata"]["kind"])
        for m in messages(mailbox)
    ]
    return [key for key in set(keys) if keys.count(key) > 1]


def replace_run(path: str) -> None:
    other = sqlite3.connect(path, timeout=0)
    other.execute("UPDATE runs SET run_id = 'run-2'")
    other.commit()
    other.close()


def unknown_intent(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: MakeContext,
    *,
    message_delivered: bool,
) -> tuple[str, Blocker]:
    """An intent in `unknown` whose message is, or is not, in the mailbox."""
    faults.fail_after_acceptance = True
    faults.empty_while_in_flight = True
    intent_id = draft_and_dispatch(store, mailbox, make_context)
    assert state_of(store, intent_id) == "unknown"
    if not message_delivered:
        mailbox.reset()
    (item,) = [b for b in open_blockers(store, LEAD) if b.kind == "delivery_unknown"]
    return intent_id, item


@pytest.fixture
def env(tmp_path: Path, mailbox: MailboxClient, leadgen: LeadgenClient) -> RunEnvironment:
    return command_environment(tmp_path, mailbox, leadgen)


@pytest.fixture
def unreachable_mailbox() -> Iterator[MailboxClient]:
    """A client for a port nothing listens on: every request fails with a connection error."""
    with httpx2.Client(base_url="http://127.0.0.1:1") as http:
        yield MailboxClient(http)


# ---- drafts -------------------------------------------------------------------------------------


def test_a_draft_holds_the_a1_fields_and_writes_intent_created(
    store: sqlite3.Connection, make_context: MakeContext
) -> None:
    intent_id = draft(store, make_context)

    row = intent_row(store, intent_id)
    assert json.loads(row.pop("ask_ids_json")) == ["acreage"]
    assert row == {
        "id": intent_id,
        "run_id": "run-1",
        "lead_id": LEAD,
        "round": 1,
        "kind": "routine_request",
        "recipient": RECIPIENT,
        "subject": "Subject",
        "body": "Body",
        "payload_hash": payload_hash(RECIPIENT, "Subject", "Body"),
        "state": "draft",
        "mailbox_id": None,
        "lead_revision": REVISION,
    }
    (created,) = events_of(store, EventType.intent_created)
    assert created.lead_id == LEAD
    assert created.payload == IntentCreated(
        intent_id=intent_id,
        round=1,
        kind="routine_request",
        recipient=RECIPIENT,
        subject="Subject",
        body="Body",
        ask_ids=["acreage"],
        payload_hash=payload_hash(RECIPIENT, "Subject", "Body"),
    )


def test_a_draft_says_whether_the_model_wrote_its_opening_and_closing(
    store: sqlite3.Connection, make_context: MakeContext
) -> None:
    for rewritten in (True, False):
        create_draft(
            store,
            make_context(),
            ASKER,
            LEAD,
            "routine_request",
            RECIPIENT,
            "Subject",
            "Body",
            ["acreage"],  # type: ignore[arg-type]
            rewritten_by_model=rewritten,
        )
        store.execute("UPDATE intents SET state = 'closed_unsent'")

    created = [e.payload for e in events_of(store, EventType.intent_created)]
    assert [c.rewritten_by_model for c in created] == [True, False]  # type: ignore[attr-defined]


def test_rounds_number_requests_only_and_a_packet_carries_the_last_request_round(
    store: sqlite3.Connection, make_context: MakeContext
) -> None:
    assert intent_row(store, draft(store, make_context, "decline_notice"))["round"] == 0
    first = draft(store, make_context, "routine_request")
    store.execute("UPDATE intents SET state = 'closed_unsent' WHERE id = ?", (first,))
    store.commit()
    again = draft(store, make_context, "routine_request")
    second = draft(store, make_context, "sensitive_request")
    packet = draft(store, make_context, "quote_packet")

    assert [intent_row(store, i)["round"] for i in (again, second, packet)] == [1, 2, 2]


def test_a_draft_whose_class_runs_at_review_waits_as_a_draft_item_and_one_at_auto_does_not(
    store: sqlite3.Connection, make_context: MakeContext
) -> None:
    routine = draft(store, make_context, "routine_request")
    sensitive = draft(store, make_context, "sensitive_request")
    packet = draft(store, make_context, "quote_packet")

    assert draft_items(store, routine) == []
    for intent_id in (sensitive, packet):
        (item,) = draft_items(store, intent_id)
        assert item.owner == "underwriter"


def test_a_draft_of_a_class_the_manifest_does_not_declare_is_refused_and_writes_nothing(
    store: sqlite3.Connection, make_context: MakeContext
) -> None:
    manifest = skill_manifest("send_routine_request")
    events_before = len(read_events(store))

    with pytest.raises(ValueError, match="does not declare send_quote_packet"):
        create_draft(store, make_context(), manifest, LEAD, "quote_packet", RECIPIENT, "S", "B", [])

    assert store.execute("SELECT count(*) FROM intents").fetchone() == (0,)
    assert len(read_events(store)) == events_before


# ---- edit_draft ---------------------------------------------------------------------------------


def test_an_edit_of_a_routine_request_makes_it_a_sensitive_request_that_waits_for_approval(
    store: sqlite3.Connection, make_context: MakeContext
) -> None:
    intent_id = draft(store, make_context, "routine_request")
    assert draft_items(store, intent_id) == []

    event_id = edit_draft(store, make_context(), intent_id, "New subject", "New body", "tone")
    store.commit()

    row = intent_row(store, intent_id)
    assert (row["subject"], row["body"], row["kind"]) == (
        "New subject",
        "New body",
        "sensitive_request",
    )
    assert row["payload_hash"] == payload_hash(RECIPIENT, "New subject", "New body")
    (edited,) = events_of(store, EventType.draft_edited)
    assert edited.id == event_id
    assert edited.payload == DraftEdited(
        intent_id=intent_id,
        kind="sensitive_request",
        subject="New subject",
        body="New body",
        payload_hash=payload_hash(RECIPIENT, "New subject", "New body"),
        reason="tone",
        lead_revision=REVISION,
    )
    assert len(draft_items(store, intent_id)) == 1


def test_an_edit_voids_the_approval_of_that_draft_only_and_a_packet_keeps_its_kind(
    store: sqlite3.Connection, make_context: MakeContext
) -> None:
    edited = draft(store, make_context, "quote_packet")
    other = draft(store, make_context, "sensitive_request")
    approve_row(store, edited)
    approve_row(store, other)

    edit_draft(store, make_context(), edited, "S", "B", "reworded")
    store.commit()

    assert (approved_rows(store, edited), approved_rows(store, other)) == (0, 1)
    assert intent_row(store, edited)["kind"] == "quote_packet"


# ---- dispatch -----------------------------------------------------------------------------------


def test_dispatch_posts_with_the_metadata_records_the_mailbox_id_and_opens_the_round(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext
) -> None:
    intent_id = draft(store, make_context)

    dispatch(store, mailbox, make_context, intent_id)

    (message,) = messages(mailbox)
    assert message["from"] == "uw@stand.com"
    assert message["to"] == RECIPIENT
    assert (message["subject"], message["body"]) == ("Subject", "Body")
    assert message["metadata"] == {
        "intent_id": intent_id,
        "run_id": "run-1",
        "kind": "routine_request",
        "round": 1,
        "payload_hash": payload_hash(RECIPIENT, "Subject", "Body"),
    }
    row = intent_row(store, intent_id)
    assert (row["state"], row["mailbox_id"]) == ("sent", message["id"])
    (sent,) = events_of(store, EventType.message_sent)
    assert sent.payload == MessageSent(intent_id=intent_id, mailbox_id=message["id"])
    (round_wait,) = open_blockers(store, LEAD)
    assert (round_wait.kind, round_wait.owner) == ("producer_reply", "producer")
    assert round_wait.detail.intent_id == intent_id


@pytest.mark.parametrize(
    ("kind", "status"), [("quote_packet", "quote_sent"), ("decline_notice", "declined")]
)
def test_a_dispatched_packet_or_notice_moves_the_lead_and_opens_no_round(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    make_context: MakeContext,
    kind: str,
    status: str,
) -> None:
    intent_id = draft(store, make_context, kind)
    approve_row(store, intent_id)

    dispatch(store, mailbox, make_context, intent_id)

    assert state_of(store, intent_id) == "sent"
    assert store.execute("SELECT status FROM leads").fetchone() == (status,)
    assert open_blockers(store, LEAD) == []


def test_a_packet_the_lead_status_does_not_allow_is_not_posted_and_returns_to_review(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext
) -> None:
    intent_id = draft(store, make_context, "quote_packet")
    approve_row(store, intent_id)
    store.execute("UPDATE leads SET status = 'quote_sent'")
    store.commit()

    dispatch(store, mailbox, make_context, intent_id)

    assert messages(mailbox) == []
    assert state_of(store, intent_id) == "draft"
    assert approved_rows(store, intent_id) == 0
    (item,) = draft_items(store, intent_id)
    assert "quote_sent" in item.detail.text


def test_a_draft_that_needs_approval_waits_for_it_and_is_sent_once_approved(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext
) -> None:
    intent_id = draft(store, make_context, "sensitive_request")

    dispatch(store, mailbox, make_context, intent_id)

    assert messages(mailbox) == []
    assert state_of(store, intent_id) == "draft"
    assert len(draft_items(store, intent_id)) == 1

    approve_row(store, intent_id)
    dispatch(store, mailbox, make_context, intent_id)

    assert message_intents(mailbox) == [intent_id]
    assert state_of(store, intent_id) == "sent"
    assert draft_items(store, intent_id) == []


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("lead_revision", REVISION - 1),
        ("plan_hash", "q" * 64),
        ("ruleset_hash", "s" * 64),
        ("recipient", "other@example.com"),
        ("payload_hash", "h" * 64),
    ],
)
def test_a_changed_bound_value_returns_the_draft_to_review_and_nothing_is_sent(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    make_context: MakeContext,
    name: str,
    value: Any,
) -> None:
    intent_id = draft(store, make_context, "sensitive_request")
    approve_row(store, intent_id, **{name: value})

    dispatch(store, mailbox, make_context, intent_id)

    assert messages(mailbox) == []
    assert state_of(store, intent_id) == "draft"
    assert approved_rows(store, intent_id) == 0
    assert len(draft_items(store, intent_id)) == 1


def test_dispatching_committed_before_post(
    store_path: str,
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: MakeContext,
) -> None:
    intent_id = draft(store, make_context)
    seen: dict[str, Any] = {}

    def second_connection() -> None:
        other = sqlite3.connect(store_path, timeout=0)
        try:
            seen["state"] = other.execute(
                "SELECT state FROM intents WHERE id = ?", (intent_id,)
            ).fetchone()[0]
            # Fails at once if the sender still holds the write lock.
            other.execute("BEGIN IMMEDIATE")
            other.rollback()
            seen["messages_at_post"] = message_intents(mailbox)
            with pytest.raises(ValueError, match="not draft"):
                edit_draft(other, make_context(), intent_id, "S", "B", "after the commit")
            dispatch(other, mailbox, make_context, intent_id)
        finally:
            other.close()

    faults.hold_in_flight = second_connection

    dispatch(store, mailbox, make_context, intent_id)

    assert seen["state"] == "dispatching"
    assert seen["messages_at_post"] == [intent_id]
    assert message_intents(mailbox) == [intent_id]
    assert state_of(store, intent_id) == "sent"


def test_a_draft_of_a_replaced_run_is_not_posted(
    store_path: str, store: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext
) -> None:
    intent_id = draft(store, make_context)
    replace_run(store_path)

    with pytest.raises(StaleRun):
        dispatch(store, mailbox, make_context, intent_id)

    assert messages(mailbox) == []
    assert state_of(store, intent_id) == "draft"


def test_the_result_of_a_post_is_not_recorded_once_the_run_is_replaced(
    store_path: str,
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: MakeContext,
) -> None:
    intent_id = draft(store, make_context)
    events_before = len(read_events(store))
    faults.hold_in_flight = lambda: replace_run(store_path)

    with pytest.raises(StaleRun):
        dispatch(store, mailbox, make_context, intent_id)

    assert state_of(store, intent_id) == "dispatching"
    assert events_of(store, EventType.message_sent) == []
    assert open_blockers(store, LEAD) == []
    assert len(read_events(store)) == events_before


def test_message_sent_is_dated_after_the_post_began(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: MakeContext,
) -> None:
    intent_id = draft(store, make_context)
    during_post: list[datetime] = []
    faults.hold_in_flight = lambda: during_post.append(make_context().real_ts)

    dispatch(store, mailbox, make_context, intent_id)

    (sent,) = events_of(store, EventType.message_sent)
    assert sent.real_ts > during_post[0]


def test_one_sender_per_lead_a_second_dispatch_waits_until_the_first_has_finished(
    store_path: str,
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: MakeContext,
) -> None:
    first = draft(store, make_context)
    second = draft(store, make_context)
    during_first: dict[str, Any] = {}

    def other_sender() -> None:
        other = open_store(store_path)
        try:
            dispatch(other, mailbox, make_context, second)
            during_first["state"] = state_of(other, second)
            during_first["messages"] = message_intents(mailbox)
        finally:
            other.close()

    faults.hold_in_flight = other_sender
    dispatch(store, mailbox, make_context, first)
    faults.hold_in_flight = None

    assert during_first == {"state": "draft", "messages": [first]}
    dispatch(store, mailbox, make_context, second)
    assert state_of(store, second) == "sent"
    assert message_intents(mailbox) == [first, second]
    assert duplicates(mailbox) == []


def test_the_sweep_sends_every_ready_draft_of_the_lead_and_leaves_one_that_waits(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext
) -> None:
    waiting = draft(store, make_context, "sensitive_request")
    ready = draft(store, make_context, "routine_request")
    approved = draft(store, make_context, "routine_request")
    store.execute("UPDATE intents SET kind = 'sensitive_request' WHERE id = ?", (approved,))
    approve_row(store, approved)

    dispatch_ready(store, mailbox, make_context, LEAD)

    assert message_intents(mailbox) == [ready, approved]
    assert state_of(store, waiting) == "draft"


def test_a_draft_at_auto_built_in_a_command_is_posted_after_the_command_commits(
    store_path: str,
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    tmp_path: Path,
    leadgen: LeadgenClient,
) -> None:
    during_step: list[list[str]] = []

    def build_draft(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        if db.execute("SELECT 1 FROM intents").fetchone() is None:
            create_draft(
                db, context, ASKER, lead_id, "routine_request", RECIPIENT, "S", "B", ["acreage"]
            )
            during_step.append(message_intents(mailbox))

    env = command_environment(tmp_path, mailbox, leadgen, (Step("draft", build_draft),))
    lock_free: list[bool] = []

    def probe_lock() -> None:
        other = sqlite3.connect(store_path, timeout=0)
        try:
            other.execute("BEGIN IMMEDIATE")
            other.rollback()
            lock_free.append(True)
        finally:
            other.close()

    faults.hold_in_flight = probe_lock
    payload = {"lead_id": LEAD, "key": "acreage", "value": 2, "reason": "call"}

    result = submit_command(store, env, "underwriter", "resolve_fact", payload)

    assert result.accepted
    assert during_step == [[]]
    assert lock_free == [True]
    (message,) = messages(mailbox)
    assert state_of(store, message["metadata"]["intent_id"]) == "sent"


# ---- reconciliation -----------------------------------------------------------------------------


def test_restart_with_pending_draft(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext
) -> None:
    posted, never_posted = "i-posted", "i-never-posted"
    insert_dispatching(store, posted, round_=1)
    insert_dispatching(store, never_posted, round_=2)
    mailbox.send(
        LEAD,
        RECIPIENT,
        "uw@stand.com",
        "S",
        "B",
        {
            "intent_id": posted,
            "run_id": "run-1",
            "kind": "routine_request",
            "round": 1,
            "payload_hash": payload_hash(RECIPIENT, "S", "B"),
        },
    )
    pending = draft(store, make_context, "sensitive_request")
    ready_at_auto = draft(store, make_context, "routine_request")

    reconcile_dispatching(store, mailbox, make_context)

    assert state_of(store, posted) == "sent"
    assert intent_row(store, posted)["mailbox_id"] == messages(mailbox)[0]["id"]
    assert state_of(store, never_posted) == "unknown"
    assert sorted((b.kind, b.detail.intent_id) for b in open_blockers(store, LEAD)) == [
        ("delivery_unknown", never_posted),
        ("producer_reply", posted),
        ("underwriter_review", pending),
    ]
    assert draft_items(store, ready_at_auto) == []
    assert state_of(store, pending) == "draft"
    assert state_of(store, ready_at_auto) == "draft"
    assert message_intents(mailbox) == [posted]


def test_a_post_whose_result_is_lost_is_reconciled_to_sent_without_a_second_post(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: MakeContext,
) -> None:
    faults.fail_after_acceptance = True

    intent_id = draft_and_dispatch(store, mailbox, make_context)

    assert state_of(store, intent_id) == "sent"
    assert message_intents(mailbox) == [intent_id]
    assert len(events_of(store, EventType.message_sent)) == 1


def test_a_reconciliation_that_finds_no_message_of_the_intent_opens_delivery_unknown_once(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext
) -> None:
    insert_dispatching(store, "i-1", round_=1)
    mailbox.send(LEAD, RECIPIENT, "uw@stand.com", "S", "B", {"intent_id": "someone-else"})
    mailbox.send(LEAD, RECIPIENT, "uw@stand.com", "S", "B", None)

    reconcile(store, mailbox, make_context, "i-1")
    reconcile(store, mailbox, make_context, "i-1")

    assert state_of(store, "i-1") == "unknown"
    (item,) = [b for b in open_blockers(store, LEAD) if b.kind == "delivery_unknown"]
    assert (item.owner, item.detail.item_kind) == ("underwriter", "delivery_unknown")
    assert len(events_of(store, EventType.delivery_unknown)) == 1


def test_a_mailbox_that_cannot_be_reached_leaves_the_intent_unknown_and_the_lead_sends_nothing(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    unreachable_mailbox: MailboxClient,
    make_context: MakeContext,
) -> None:
    first = draft(store, make_context)

    dispatch(store, unreachable_mailbox, make_context, first)

    assert state_of(store, first) == "unknown"
    (item,) = open_blockers(store, LEAD)
    assert (item.kind, item.detail.intent_id) == ("delivery_unknown", first)
    assert messages(mailbox) == []
    second = draft(store, make_context)
    dispatch(store, mailbox, make_context, second)
    assert state_of(store, second) == "draft"
    assert messages(mailbox) == []


def test_a_draft_built_at_an_older_revision_is_not_sent_and_is_replaced(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: MakeContext
) -> None:
    stale = draft(store, make_context)
    store.execute("UPDATE leads SET revision = revision + 1 WHERE lead_id = ?", (LEAD,))
    store.commit()

    dispatch_ready(store, mailbox, make_context, LEAD)

    assert messages(mailbox) == []
    assert state_of(store, stale) == "draft"

    replace_stale_drafts(store, make_context(), LEAD)
    current = draft(store, make_context)
    dispatch_ready(store, mailbox, make_context, LEAD)

    assert state_of(store, stale) == "closed_unsent"
    assert message_intents(mailbox) == [current]


# ---- resolving delivery_unknown -----------------------------------------------------------------


def test_delivery_unknown_approve_rechecks(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: MakeContext,
    env: RunEnvironment,
) -> None:
    intent_id, item = unknown_intent(store, mailbox, faults, make_context, message_delivered=True)

    result = submit_command(
        store, env, "underwriter", "approve", {"item_id": item.id, "reason": "looked"}
    )

    assert result.accepted
    (message,) = messages(mailbox)
    assert message["metadata"]["intent_id"] == intent_id
    row = intent_row(store, intent_id)
    assert (row["state"], row["mailbox_id"]) == ("sent", message["id"])
    assert [b.kind for b in open_blockers(store, LEAD)] == ["producer_reply"]
    approval = store.execute(
        "SELECT item_kind, intent_id, decision, actor, recipient, payload_hash FROM approvals"
    ).fetchone()
    assert approval == (
        "delivery_unknown",
        intent_id,
        "approved",
        "underwriter",
        RECIPIENT,
        payload_hash(RECIPIENT, "Subject", "Body"),
    )
    assert duplicates(mailbox) == []


def test_delivery_unknown_reject_closes_unsent(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: MakeContext,
    env: RunEnvironment,
) -> None:
    intent_id, item = unknown_intent(store, mailbox, faults, make_context, message_delivered=False)

    result = submit_command(
        store, env, "underwriter", "reject", {"item_id": item.id, "reason": "never arrived"}
    )

    assert result.accepted
    assert state_of(store, intent_id) == "closed_unsent"
    (fresh_id,) = [
        r[0] for r in store.execute("SELECT id FROM intents WHERE state = 'draft'").fetchall()
    ]
    old, fresh = intent_row(store, intent_id), intent_row(store, fresh_id)
    for column in ("round", "kind", "recipient", "subject", "body", "ask_ids_json", "payload_hash"):
        assert fresh[column] == old[column]
    assert fresh["id"] != intent_id
    (created,) = [
        e for e in events_of(store, EventType.intent_created) if e.payload.intent_id == fresh_id
    ]
    assert created.actor == "workflow"
    assert len(draft_items(store, fresh_id)) == 1
    assert [b.kind for b in open_blockers(store, LEAD)] == ["underwriter_review"]
    assert messages(mailbox) == []  # a class at auto does not send a draft that waits for approval
    approval = store.execute("SELECT item_kind, intent_id, decision FROM approvals").fetchone()
    assert approval == ("delivery_unknown", intent_id, "rejected")


def test_a_draft_for_a_round_closed_after_an_unknown_delivery_waits_for_approval(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: MakeContext,
    env: RunEnvironment,
) -> None:
    _, item = unknown_intent(store, mailbox, faults, make_context, message_delivered=False)
    assert submit_command(
        store, env, "underwriter", "reject", {"item_id": item.id, "reason": "never arrived"}
    ).accepted
    store.execute(
        "UPDATE leads SET revision = revision + 1 WHERE lead_id = ?", (LEAD,)
    )  # a late reply
    store.commit()
    replace_stale_drafts(store, make_context(), LEAD)
    rebuilt = draft(store, make_context)

    dispatch_ready(store, mailbox, make_context, LEAD)

    assert intent_row(store, rebuilt)["round"] == 1
    assert len(draft_items(store, rebuilt)) == 1
    assert state_of(store, rebuilt) == "draft"
    assert messages(mailbox) == []


# ---- a result recorded after another command settled the intent ---------------------------------


def test_a_delivery_found_after_a_reject_closed_the_intent_is_not_recorded_as_sent(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: MakeContext,
    env: RunEnvironment,
) -> None:
    intent_id, item = unknown_intent(store, mailbox, faults, make_context, message_delivered=True)
    read_before_the_reject = read_intent(store, intent_id)
    assert read_before_the_reject is not None

    assert submit_command(
        store, env, "underwriter", "reject", {"item_id": item.id, "reason": "not there"}
    ).accepted
    _record_sent(store, mailbox, make_context, read_before_the_reject, 99)

    assert state_of(store, intent_id) == "closed_unsent"
    assert intent_row(store, intent_id)["mailbox_id"] is None
    assert events_of(store, EventType.message_sent) == []
    assert [b.kind for b in open_blockers(store, LEAD)] == ["underwriter_review"]


def test_two_approvals_of_one_delivery_record_one_message_sent_and_one_round_wait(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: MakeContext,
) -> None:
    intent_id, _ = unknown_intent(store, mailbox, faults, make_context, message_delivered=True)
    read_by_both = read_intent(store, intent_id)
    assert read_by_both is not None
    (message,) = messages(mailbox)

    _record_sent(store, mailbox, make_context, read_by_both, message["id"])
    _record_sent(store, mailbox, make_context, read_by_both, message["id"])

    assert state_of(store, intent_id) == "sent"
    assert len(events_of(store, EventType.message_sent)) == 1
    assert [b.kind for b in open_blockers(store, LEAD)] == ["producer_reply"]
