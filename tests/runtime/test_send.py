# ABOUTME: Tests the send primitive of 7.5 against Stand's mailbox in process: drafts and their rounds, edit_draft, the dispatch that commits `dispatching` before the post, one sender per lead, reconciliation, and the resolution of `delivery_unknown`.
# ABOUTME: Each test opens a real database, posts to the real mailbox app and reads the mailbox and the event log back; a lead and a message are keyed by lead id and intent id, never the mailbox row id.
import json
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

import httpx2
import pytest

from tests.runtime.helpers import ASKER, PLAN_HASH, REVISION, RULESET
from tests.runtime.helpers import LEAD_ID as LEAD
from uwh.runtime.commands import CommandEnvironment, _send_after_commit, submit_command
from uwh.runtime.event_types import (
    DraftEdited,
    EventType,
    IntentCreated,
    MessageSent,
    RequestKind,
)
from uwh.runtime.events import EventContext, StaleRun, StoredEvent, read_events
from uwh.runtime.facts import LedgerRules
from uwh.runtime.faults import FaultPlan
from uwh.runtime.hashing import payload_hash
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.send import (
    create_draft,
    dispatch,
    dispatch_ready,
    edit_draft,
    read_intent,
    reconcile,
    reconcile_dispatching,
)
from uwh.runtime.send import _record_sent, _record_unknown
from uwh.runtime.store import open_store
from uwh.runtime.waits import Blocker, open_blockers
from uwh.runtime.workflow import Step

RECIPIENT = "producer@example.com"
NOW = datetime(2026, 10, 5, 12, 5, tzinfo=UTC)
Context = Callable[[], EventContext]


def draft(
    db: sqlite3.Connection,
    context: Context,
    kind: str = "routine_request",
    subject: str = "Subject",
    body: str = "Body",
    ask_ids: list[str] | None = None,
) -> str:
    intent_id = create_draft(
        db,
        context(),
        ASKER,
        LEAD,
        kind,
        RECIPIENT,
        subject,
        body,
        ask_ids or ["acreage"],  # type: ignore[arg-type]
    )
    db.commit()
    return intent_id


def intent_row(db: sqlite3.Connection, intent_id: str) -> dict[str, Any]:
    cursor = db.execute("SELECT * FROM intents WHERE id = ?", (intent_id,))
    names = [column[0] for column in cursor.description]
    return dict(zip(names, cursor.fetchone(), strict=True))


def state_of(db: sqlite3.Connection, intent_id: str) -> str:
    return str(intent_row(db, intent_id)["state"])


def events_of(db: sqlite3.Connection, event_type: EventType) -> list[StoredEvent]:
    return [e for e in read_events(db) if e.type == event_type]


def messages(mailbox: MailboxClient) -> list[dict[str, Any]]:
    return sorted(
        mailbox.list_for_lead(LEAD), key=lambda m: m["id"]
    )  # the mailbox lists newest first


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


@pytest.fixture
def env(tmp_path: Path, mailbox: MailboxClient, leadgen: LeadgenClient) -> CommandEnvironment:
    return CommandEnvironment(
        "replay", RULESET, LedgerRules(), (), tmp_path, lambda: NOW, mailbox, leadgen
    )


# ---- creating a draft ---------------------------------------------------------------------------


def test_a_draft_holds_the_a1_fields_and_writes_intent_created(
    store: sqlite3.Connection, make_context: Context
) -> None:
    intent_id = draft(store, make_context, ask_ids=["acreage", "q:roof"])

    row = intent_row(store, intent_id)
    assert json.loads(row.pop("ask_ids_json")) == ["acreage", "q:roof"]
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
        ask_ids=["acreage", "q:roof"],
        payload_hash=payload_hash(RECIPIENT, "Subject", "Body"),
    )


def test_rounds_number_requests_only_and_a_packet_carries_the_last_request_round(
    store: sqlite3.Connection, make_context: Context
) -> None:
    first = draft(store, make_context, "routine_request")
    second = draft(store, make_context, "sensitive_request")
    packet = draft(store, make_context, "quote_packet")

    assert [intent_row(store, i)["round"] for i in (first, second, packet)] == [1, 2, 2]


def test_a_packet_or_notice_with_no_request_behind_it_is_round_0(
    store: sqlite3.Connection, make_context: Context
) -> None:
    packet = draft(store, make_context, "quote_packet")
    notice = draft(store, make_context, "decline_notice")

    assert [intent_row(store, i)["round"] for i in (packet, notice)] == [0, 0]


def test_a_request_closed_unsent_does_not_count_toward_the_round(
    store: sqlite3.Connection, make_context: Context
) -> None:
    first = draft(store, make_context)
    store.execute("UPDATE intents SET state = 'closed_unsent' WHERE id = ?", (first,))
    store.commit()

    assert intent_row(store, draft(store, make_context))["round"] == 1


def test_a_draft_whose_class_runs_at_review_waits_as_a_draft_item_and_one_at_auto_does_not(
    store: sqlite3.Connection, make_context: Context
) -> None:
    routine = draft(store, make_context, "routine_request")
    sensitive = draft(store, make_context, "sensitive_request")
    packet = draft(store, make_context, "quote_packet")

    assert draft_items(store, routine) == []
    for intent_id in (sensitive, packet):
        (item,) = draft_items(store, intent_id)
        assert item.owner == "underwriter"


def test_a_draft_of_a_class_the_manifest_does_not_declare_is_refused_and_writes_nothing(
    store: sqlite3.Connection, make_context: Context
) -> None:
    manifest = ASKER.model_copy(update={"command_classes": ["send_routine_request"]})
    events_before = len(read_events(store))

    with pytest.raises(ValueError, match="does not declare send_quote_packet"):
        create_draft(store, make_context(), manifest, LEAD, "quote_packet", RECIPIENT, "S", "B", [])

    assert store.execute("SELECT count(*) FROM intents").fetchone() == (0,)
    assert len(read_events(store)) == events_before


# ---- edit_draft ---------------------------------------------------------------------------------


def test_edit_replaces_subject_body_and_hash_and_writes_the_resulting_kind(
    store: sqlite3.Connection, make_context: Context
) -> None:
    intent_id = draft(store, make_context, "quote_packet")

    event_id = edit_draft(store, make_context(), intent_id, "New subject", "New body", "tone")
    store.commit()

    row = intent_row(store, intent_id)
    assert (row["subject"], row["body"], row["kind"]) == ("New subject", "New body", "quote_packet")
    assert row["payload_hash"] == payload_hash(RECIPIENT, "New subject", "New body")
    (edited,) = events_of(store, EventType.draft_edited)
    assert edited.id == event_id
    assert edited.payload == DraftEdited(
        intent_id=intent_id,
        kind="quote_packet",
        subject="New subject",
        body="New body",
        payload_hash=payload_hash(RECIPIENT, "New subject", "New body"),
        reason="tone",
        lead_revision=REVISION,
    )


def test_an_edited_routine_request_becomes_a_sensitive_request_that_waits_for_approval(
    store: sqlite3.Connection, make_context: Context
) -> None:
    intent_id = draft(store, make_context, "routine_request")
    assert draft_items(store, intent_id) == []

    edit_draft(store, make_context(), intent_id, "S", "B", "reworded")
    store.commit()

    assert intent_row(store, intent_id)["kind"] == "sensitive_request"
    (edited,) = events_of(store, EventType.draft_edited)
    assert isinstance(edited.payload, DraftEdited) and edited.payload.kind == "sensitive_request"
    assert len(draft_items(store, intent_id)) == 1


def test_a_decline_notice_keeps_its_kind_when_edited(
    store: sqlite3.Connection, make_context: Context
) -> None:
    intent_id = draft(store, make_context, "decline_notice")

    edit_draft(store, make_context(), intent_id, "S", "B", "reworded")

    assert intent_row(store, intent_id)["kind"] == "decline_notice"


def test_an_edit_voids_the_approval_of_the_draft(
    store: sqlite3.Connection, make_context: Context
) -> None:
    intent_id = draft(store, make_context, "sensitive_request")
    approve_row(store, intent_id)
    assert approved_rows(store, intent_id) == 1

    edit_draft(store, make_context(), intent_id, "S", "B", "reworded")
    store.commit()

    assert approved_rows(store, intent_id) == 0


def test_an_edit_leaves_the_approvals_of_other_drafts(
    store: sqlite3.Connection, make_context: Context
) -> None:
    edited = draft(store, make_context, "sensitive_request")
    other = draft(store, make_context, "sensitive_request")
    approve_row(store, other)

    edit_draft(store, make_context(), edited, "S", "B", "reworded")

    assert approved_rows(store, other) == 1


def test_a_draft_that_has_left_draft_cannot_be_edited(
    store: sqlite3.Connection, make_context: Context
) -> None:
    intent_id = draft(store, make_context, "routine_request")
    store.execute("UPDATE intents SET state = 'dispatching' WHERE id = ?", (intent_id,))
    store.commit()

    with pytest.raises(ValueError, match="not draft"):
        edit_draft(store, make_context(), intent_id, "S", "B", "late")

    assert intent_row(store, intent_id)["subject"] == "Subject"


# ---- dispatch -----------------------------------------------------------------------------------


def test_dispatch_posts_with_the_metadata_records_the_mailbox_id_and_opens_the_round(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: Context
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
    make_context: Context,
    kind: str,
    status: str,
) -> None:
    intent_id = draft(store, make_context, kind)
    approve_row(store, intent_id)

    dispatch(store, mailbox, make_context, intent_id)

    assert state_of(store, intent_id) == "sent"
    assert store.execute("SELECT status FROM leads").fetchone() == (status,)
    assert [b.kind for b in open_blockers(store, LEAD)] == []


def test_a_packet_the_lead_status_does_not_allow_is_not_posted_and_returns_to_review_with_the_reason(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: Context
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


def test_dispatch_refuses_to_run_inside_a_transaction(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: Context
) -> None:
    intent_id = draft(store, make_context)
    store.execute("BEGIN")

    with pytest.raises(RuntimeError, match="transaction"):
        dispatch(store, mailbox, make_context, intent_id)
    store.rollback()

    assert messages(mailbox) == []


def test_a_draft_that_needs_approval_and_has_none_is_not_sent(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: Context
) -> None:
    intent_id = draft(store, make_context, "sensitive_request")

    dispatch(store, mailbox, make_context, intent_id)

    assert messages(mailbox) == []
    assert state_of(store, intent_id) == "draft"
    assert len(draft_items(store, intent_id)) == 1


def test_an_approved_draft_is_sent_and_its_item_closes(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: Context
) -> None:
    intent_id = draft(store, make_context, "sensitive_request")
    approve_row(store, intent_id)

    dispatch(store, mailbox, make_context, intent_id)

    assert message_intents(mailbox) == [intent_id]
    assert state_of(store, intent_id) == "sent"
    assert draft_items(store, intent_id) == []


MISMATCHES: list[tuple[str, Any]] = [
    ("lead_revision", REVISION - 1),
    ("plan_hash", "q" * 64),
    ("ruleset_hash", "s" * 64),
    ("recipient", "other@example.com"),
    ("payload_hash", "h" * 64),
]


@pytest.mark.parametrize(("name", "value"), MISMATCHES)
def test_a_changed_bound_value_returns_the_draft_to_review_and_nothing_is_sent(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    make_context: Context,
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


def test_a_mismatch_reopens_the_item_when_it_is_closed(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: Context
) -> None:
    intent_id = draft(store, make_context, "sensitive_request")
    approve_row(store, intent_id, lead_revision=REVISION - 1)
    store.execute("UPDATE blockers SET closed_event_id = 0")
    store.commit()
    assert draft_items(store, intent_id) == []

    dispatch(store, mailbox, make_context, intent_id)

    assert len(draft_items(store, intent_id)) == 1


def test_dispatching_committed_before_post(
    store_path: str,
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Context,
) -> None:
    intent_id = draft(store, make_context)
    seen: dict[str, Any] = {}

    def second_connection() -> None:
        other = sqlite3.connect(store_path, timeout=0)
        try:
            seen["state"] = other.execute(
                "SELECT state FROM intents WHERE id = ?", (intent_id,)
            ).fetchone()[0]
            other.execute(
                "BEGIN IMMEDIATE"
            )  # fails at once if the sender still holds the write lock
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


def replace_run(path: str) -> None:
    other = sqlite3.connect(path, timeout=0)
    other.execute("UPDATE runs SET run_id = 'run-2'")
    other.commit()
    other.close()


def test_a_draft_of_a_replaced_run_is_not_posted(
    store_path: str, store: sqlite3.Connection, mailbox: MailboxClient, make_context: Context
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
    make_context: Context,
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


def test_a_delivery_that_turns_out_unknown_after_the_run_is_replaced_writes_nothing(
    store_path: str,
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Context,
) -> None:
    intent_id = draft(store, make_context)
    events_before = len(read_events(store))
    faults.fail_after_acceptance = True
    faults.empty_while_in_flight = True
    faults.hold_in_flight = lambda: replace_run(store_path)

    with pytest.raises(StaleRun):
        dispatch(store, mailbox, make_context, intent_id)

    assert events_of(store, EventType.delivery_unknown) == []
    assert events_of(store, EventType.message_sent) == []
    assert open_blockers(store, LEAD) == []
    assert len(read_events(store)) == events_before


def test_message_sent_is_dated_after_the_post_began(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Context,
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
    make_context: Context,
) -> None:
    first = draft(store, make_context, "routine_request")
    second = draft(store, make_context, "routine_request")
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
    assert state_of(store, first) == "sent"
    dispatch(store, mailbox, make_context, second)
    assert state_of(store, second) == "sent"
    assert message_intents(mailbox) == [first, second]
    assert duplicates(mailbox) == []


def test_the_sweep_sends_every_ready_draft_of_the_lead_and_leaves_one_that_waits(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: Context
) -> None:
    waiting = draft(store, make_context, "sensitive_request")
    ready = draft(store, make_context, "routine_request")
    approved = draft(store, make_context, "routine_request")
    store.execute("UPDATE intents SET kind = 'sensitive_request' WHERE id = ?", (approved,))
    approve_row(store, approved)

    dispatch_ready(store, mailbox, make_context, LEAD)

    assert message_intents(mailbox) == [ready, approved]
    assert state_of(store, waiting) == "draft"


def test_the_sweep_sends_a_draft_that_was_skipped_while_another_dispatch_was_in_flight(
    store_path: str,
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Context,
) -> None:
    first = draft(store, make_context, "routine_request")
    second = draft(store, make_context, "routine_request")

    def other_sweep() -> None:
        other = open_store(store_path)
        try:
            dispatch_ready(other, mailbox, make_context, LEAD)
        finally:
            other.close()

    faults.hold_in_flight = other_sweep
    dispatch_ready(store, mailbox, make_context, LEAD)

    assert sorted(message_intents(mailbox)) == sorted([first, second])
    assert duplicates(mailbox) == []


# ---- reconciliation -----------------------------------------------------------------------------


def insert_dispatching(db: sqlite3.Connection, intent_id: str, *, round_: int) -> None:
    """An intent as a stopped process leaves it: `dispatching`, the post made or not."""
    db.execute(
        "INSERT INTO intents (id, run_id, lead_id, round, kind, recipient, subject, body,"
        " ask_ids_json, payload_hash, state) VALUES (?, 'run-1', ?, ?, 'routine_request', ?, 'S',"
        " 'B', '[]', ?, 'dispatching')",
        (intent_id, LEAD, round_, RECIPIENT, payload_hash(RECIPIENT, "S", "B")),
    )
    db.commit()


def test_restart_with_pending_draft(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: Context
) -> None:
    posted, never_posted = "i-posted", "i-never-posted"
    insert_dispatching(store, posted, round_=1)
    insert_dispatching(store, never_posted, round_=2)
    mailbox.send(
        LEAD, RECIPIENT, "uw@stand.com", "S", "B",
        {"intent_id": posted, "run_id": "run-1", "kind": "routine_request", "round": 1,
         "payload_hash": payload_hash(RECIPIENT, "S", "B")},
    )  # fmt: skip
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


def test_reconcile_matches_on_the_intent_id_in_the_metadata(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: Context
) -> None:
    insert_dispatching(store, "i-1", round_=1)
    mailbox.send(LEAD, RECIPIENT, "uw@stand.com", "S", "B", {"intent_id": "someone-else"})
    mailbox.send(LEAD, RECIPIENT, "uw@stand.com", "S", "B", None)

    reconcile(store, mailbox, make_context, "i-1")

    assert state_of(store, "i-1") == "unknown"


def test_a_reconciliation_that_finds_no_message_opens_delivery_unknown_once(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: Context
) -> None:
    insert_dispatching(store, "i-1", round_=1)

    reconcile(store, mailbox, make_context, "i-1")
    reconcile(store, mailbox, make_context, "i-1")

    (item,) = [b for b in open_blockers(store, LEAD) if b.kind == "delivery_unknown"]
    assert item.owner == "underwriter"
    assert item.detail.item_kind == "delivery_unknown"
    assert len(events_of(store, EventType.delivery_unknown)) == 1


def test_reconcile_refuses_inside_a_transaction(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: Context
) -> None:
    insert_dispatching(store, "i-1", round_=1)
    store.execute("BEGIN")

    with pytest.raises(RuntimeError, match="transaction"):
        reconcile(store, mailbox, make_context, "i-1")
    store.rollback()


def test_reconcile_refuses_an_intent_that_is_neither_dispatching_nor_unknown(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: Context
) -> None:
    intent_id = draft(store, make_context)

    with pytest.raises(ValueError, match="draft"):
        reconcile(store, mailbox, make_context, intent_id)


# ---- resolving delivery_unknown -----------------------------------------------------------------


def unknown_intent(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Context,
    *,
    message_delivered: bool,
    kind: str = "routine_request",
) -> tuple[str, Blocker]:
    """An intent in `unknown` whose message is, or is not, in the mailbox."""
    faults.fail_after_acceptance = True
    faults.empty_while_in_flight = True
    intent_id = draft(store, make_context, kind)
    dispatch(store, mailbox, make_context, intent_id)
    assert state_of(store, intent_id) == "unknown"
    if not message_delivered:
        mailbox.reset()
    (item,) = [b for b in open_blockers(store, LEAD) if b.kind == "delivery_unknown"]
    return intent_id, item


def test_delivery_unknown_approve_rechecks(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Context,
    env: CommandEnvironment,
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


def test_delivery_unknown_approve_with_no_message_in_the_mailbox_stays_unknown(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Context,
    env: CommandEnvironment,
) -> None:
    intent_id, item = unknown_intent(store, mailbox, faults, make_context, message_delivered=False)

    result = submit_command(
        store, env, "underwriter", "approve", {"item_id": item.id, "reason": "looked"}
    )

    assert result.accepted
    assert state_of(store, intent_id) == "unknown"
    assert [b.id for b in open_blockers(store, LEAD)] == [item.id]
    assert messages(mailbox) == []
    assert len(events_of(store, EventType.delivery_unknown)) == 1


def test_delivery_unknown_reject_closes_unsent(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Context,
    env: CommandEnvironment,
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


def test_a_reject_of_delivery_unknown_needs_a_reason(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Context,
    env: CommandEnvironment,
) -> None:
    intent_id, item = unknown_intent(store, mailbox, faults, make_context, message_delivered=False)

    result = submit_command(store, env, "underwriter", "reject", {"item_id": item.id, "reason": ""})

    assert not result.accepted
    assert state_of(store, intent_id) == "unknown"


# ---- dispatch after a command -------------------------------------------------------------------


def test_a_draft_at_auto_built_in_a_command_is_posted_after_the_command_commits(
    store_path: str,
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Context,
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

    env = CommandEnvironment(
        "replay",
        RULESET,
        LedgerRules(),
        (Step("draft", build_draft),),
        tmp_path,
        lambda: NOW,
        mailbox,
        leadgen,
    )
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


def test_a_draft_at_review_built_in_a_command_is_not_posted(
    store: sqlite3.Connection, mailbox: MailboxClient, tmp_path: Path, leadgen: LeadgenClient
) -> None:
    def build_draft(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        if db.execute("SELECT 1 FROM intents").fetchone() is None:
            create_draft(db, context, ASKER, lead_id, "sensitive_request", RECIPIENT, "S", "B", [])

    env = CommandEnvironment(
        "replay",
        RULESET,
        LedgerRules(),
        (Step("draft", build_draft),),
        tmp_path,
        lambda: NOW,
        mailbox,
        leadgen,
    )
    payload = {"lead_id": LEAD, "key": "acreage", "value": 2, "reason": "call"}

    assert submit_command(store, env, "underwriter", "resolve_fact", payload).accepted

    assert messages(mailbox) == []
    assert len(open_blockers(store, LEAD)) == 1


# ---- a result recorded after another command settled the intent ---------------------------------


def test_a_delivery_found_after_a_reject_closed_the_intent_is_not_recorded_as_sent(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Context,
    env: CommandEnvironment,
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
    make_context: Context,
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


def test_an_intent_another_reconciliation_marked_unknown_is_not_marked_unknown_again(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: Context
) -> None:
    insert_dispatching(store, "i-1", round_=1)
    read_by_both = read_intent(store, "i-1")
    assert read_by_both is not None

    _record_unknown(store, mailbox, make_context, read_by_both)
    _record_unknown(store, mailbox, make_context, read_by_both)

    assert state_of(store, "i-1") == "unknown"
    assert len(events_of(store, EventType.delivery_unknown)) == 1
    assert [b.kind for b in open_blockers(store, LEAD)] == ["delivery_unknown"]


def test_a_recheck_of_an_intent_another_command_closed_unsent_changes_nothing(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Context,
    env: CommandEnvironment,
) -> None:
    intent_id, item = unknown_intent(store, mailbox, faults, make_context, message_delivered=True)
    assert submit_command(
        store, env, "underwriter", "reject", {"item_id": item.id, "reason": "not there"}
    ).accepted

    _send_after_commit(store, env, make_context, LEAD, intent_id)

    assert state_of(store, intent_id) == "closed_unsent"
    assert events_of(store, EventType.message_sent) == []


# ---- a mailbox that cannot be read --------------------------------------------------------------


@pytest.fixture
def unreachable_mailbox() -> Iterator[MailboxClient]:
    """A client for a port nothing listens on: every request fails with a connection error."""
    with httpx2.Client(base_url="http://127.0.0.1:1") as http:
        yield MailboxClient(http)


def test_a_mailbox_that_cannot_be_reached_leaves_the_intent_unknown_with_a_blocker_and_no_message(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    unreachable_mailbox: MailboxClient,
    make_context: Context,
) -> None:
    first = draft(store, make_context)

    dispatch(store, unreachable_mailbox, make_context, first)

    assert state_of(store, first) == "unknown"
    (item,) = open_blockers(store, LEAD)
    assert (item.kind, item.detail.intent_id) == ("delivery_unknown", first)
    assert messages(mailbox) == []
    second = draft(store, make_context)
    dispatch(store, mailbox, make_context, second)
    assert state_of(store, second) == "sent"
    assert message_intents(mailbox) == [second]


def test_startup_with_the_mailbox_down_leaves_a_dispatching_intent_unknown(
    store: sqlite3.Connection, unreachable_mailbox: MailboxClient, make_context: Context
) -> None:
    insert_dispatching(store, "i-1", round_=1)

    reconcile_dispatching(store, unreachable_mailbox, make_context)

    assert state_of(store, "i-1") == "unknown"
    assert [b.kind for b in open_blockers(store, LEAD)] == ["delivery_unknown"]


def test_approving_delivery_unknown_with_the_mailbox_down_is_accepted_and_the_item_stays_open(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    unreachable_mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Context,
    env: CommandEnvironment,
) -> None:
    intent_id, item = unknown_intent(store, mailbox, faults, make_context, message_delivered=True)

    result = submit_command(
        store,
        replace(env, mailbox=unreachable_mailbox),
        "underwriter",
        "approve",
        {"item_id": item.id, "reason": "looked"},
    )

    assert result.accepted
    assert state_of(store, intent_id) == "unknown"
    assert [b.id for b in open_blockers(store, LEAD)] == [item.id]
    (approval,) = store.execute("SELECT item_kind, decision FROM approvals").fetchall()
    assert approval == ("delivery_unknown", "approved")


# ---- nothing after a commit raises --------------------------------------------------------------


def set_status_elsewhere(path: str, status: str) -> None:
    other = sqlite3.connect(path, timeout=0)
    other.execute("UPDATE leads SET status = ?", (status,))
    other.commit()
    other.close()


def test_a_sent_packet_is_recorded_though_the_lead_status_changed_during_the_post(
    store_path: str,
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Context,
) -> None:
    intent_id = draft(store, make_context, "quote_packet")
    approve_row(store, intent_id)
    faults.hold_in_flight = lambda: set_status_elsewhere(store_path, "declined")

    dispatch(store, mailbox, make_context, intent_id)

    assert message_intents(mailbox) == [intent_id]
    assert state_of(store, intent_id) == "sent"
    assert len(events_of(store, EventType.message_sent)) == 1
    assert store.execute("SELECT status FROM leads").fetchone() == ("declined",)


def test_a_command_is_accepted_when_its_dispatch_finds_the_lead_status_refusing_the_packet(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    make_context: Context,
    env: CommandEnvironment,
) -> None:
    intent_id = draft(store, make_context, "quote_packet")
    approve_row(store, intent_id)
    store.execute("UPDATE leads SET status = 'quote_sent'")
    store.commit()
    payload = {"lead_id": LEAD, "key": "acreage", "value": 2, "reason": "call"}

    assert submit_command(store, env, "underwriter", "resolve_fact", payload).accepted
    assert submit_command(store, env, "underwriter", "resolve_fact", payload).accepted

    assert messages(mailbox) == []
    assert state_of(store, intent_id) == "draft"
    assert len(draft_items(store, intent_id)) == 1


def test_a_step_that_drafts_a_class_its_manifest_does_not_declare_fails_and_the_command_commits(
    store: sqlite3.Connection, mailbox: MailboxClient, tmp_path: Path, leadgen: LeadgenClient
) -> None:
    manifest = ASKER.model_copy(update={"command_classes": ["send_routine_request"]})

    def build_draft(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        create_draft(db, context, manifest, lead_id, "quote_packet", RECIPIENT, "S", "B", [])

    env = CommandEnvironment(
        "replay",
        RULESET,
        LedgerRules(),
        (Step("draft", build_draft),),
        tmp_path,
        lambda: NOW,
        mailbox,
        leadgen,
    )
    payload = {"lead_id": LEAD, "key": "acreage", "value": 2, "reason": "call"}

    assert submit_command(store, env, "underwriter", "resolve_fact", payload).accepted

    assert store.execute("SELECT count(*) FROM intents").fetchone() == (0,)
    (failure,) = open_blockers(store, LEAD)
    assert (failure.kind, "does not declare send_quote_packet" in failure.detail.text) == (
        "data",
        True,
    )
