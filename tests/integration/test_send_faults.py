# ABOUTME: Integration tests of the send faults of 7.5 and 13.1 against Stand's running mailbox container: a result lost after acceptance, an empty listing while a post is in flight, and the startup reconcile.
# ABOUTME: Each test uses its own TEST- lead id and never resets the container; messages are counted per intent id from the container's own listing, not from the sender's return values.
import sqlite3
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path

import httpx2
import pytest

from tests.runtime.helpers import ASKER, PLAN_HASH, REVISION, RULESET, RUN_START
from uwh.runtime.event_types import EventType, FaultInjected
from uwh.runtime.events import EventContext, read_events
from uwh.runtime.faults import FaultPlan
from uwh.runtime.hashing import payload_hash
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.send import create_draft, dispatch, reconcile, reconcile_dispatching
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blockers
from uwh.skills.vertical import REFERENCE_MORNING

pytestmark = pytest.mark.integration

RECIPIENT = "p@example.com"


@pytest.fixture
def lead_id() -> str:
    return f"TEST-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def container(host_urls: dict[str, str]) -> Iterator[httpx2.Client]:
    """A plain client of the mailbox container, used to count what the container holds."""
    with httpx2.Client(base_url=host_urls["mailbox"]) as http:
        yield http


@pytest.fixture
def faults() -> FaultPlan:
    return FaultPlan()


@pytest.fixture
def mailbox(container: httpx2.Client, faults: FaultPlan) -> MailboxClient:
    return MailboxClient(container, faults)


@pytest.fixture
def store(tmp_path: Path, lead_id: str) -> Iterator[sqlite3.Connection]:
    """A database on a temporary path with the current run and one in-progress lead."""
    db = open_store(str(tmp_path / "app.db"))
    db.execute(
        "INSERT INTO runs (run_id, seed, mode, started_at, status)"
        " VALUES ('run-1', 42, 'replay', '2026-10-05T12:00:00.000000Z', 'processing')"
    )
    db.execute(
        "INSERT INTO leads (lead_id, run_id, source, received_at, status, revision, plan_hash)"
        " VALUES (?, 'run-1', 'web', '2026-06-29T07:00:00Z', 'in_progress', ?, ?)",
        (lead_id, REVISION, PLAN_HASH),
    )
    db.commit()
    yield db
    db.close()


@pytest.fixture
def make_context() -> Callable[[], EventContext]:
    """Each call returns a context one second later than the call before."""
    calls = 0

    def next_context() -> EventContext:
        nonlocal calls
        calls += 1
        return EventContext(
            "run-1",
            "replay",
            "workflow",
            RULESET,
            RUN_START + timedelta(seconds=calls),
            REFERENCE_MORNING + timedelta(seconds=calls),
        )

    return next_context


def held_intents(container: httpx2.Client, lead_id: str) -> list[str]:
    """The intent id of every message the container holds for the lead, sorted."""
    response = container.get(f"/leads/{lead_id}/emails")
    response.raise_for_status()
    return sorted(m["metadata"]["intent_id"] for m in response.json())


def state_of(db: sqlite3.Connection, intent_id: str) -> str:
    (state,) = db.execute("SELECT state FROM intents WHERE id = ?", (intent_id,)).fetchone()
    return str(state)


def injected(db: sqlite3.Connection) -> list[str]:
    return [
        e.payload.fault
        for e in read_events(db)
        if e.type == EventType.fault_injected and isinstance(e.payload, FaultInjected)
    ]


def draft_and_dispatch(
    db: sqlite3.Connection,
    mailbox: MailboxClient,
    make_context: Callable[[], EventContext],
    lead_id: str,
) -> str:
    intent_id = create_draft(
        db, make_context(), ASKER, lead_id, "routine_request", RECIPIENT, "Subject", "Body", []
    )
    db.commit()
    dispatch(db, mailbox, make_context, intent_id)
    return intent_id


def insert_dispatching(db: sqlite3.Connection, lead_id: str, intent_id: str, round_: int) -> None:
    """An intent as a stopped process leaves it: `dispatching`, the post made or not."""
    db.execute(
        "INSERT INTO intents (id, run_id, lead_id, round, kind, recipient, subject, body,"
        " ask_ids_json, payload_hash, state) VALUES (?, 'run-1', ?, ?, 'routine_request', ?, 'S',"
        " 'B', '[]', ?, 'dispatching')",
        (intent_id, lead_id, round_, RECIPIENT, payload_hash(RECIPIENT, "S", "B")),
    )
    db.commit()


def test_a_lost_result_is_reconciled_to_sent_with_one_message_in_the_container(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    container: httpx2.Client,
    make_context: Callable[[], EventContext],
    lead_id: str,
) -> None:
    faults.fail_after_acceptance = True

    intent_id = draft_and_dispatch(store, mailbox, make_context, lead_id)

    assert held_intents(container, lead_id) == [intent_id]
    assert state_of(store, intent_id) == "sent"
    assert injected(store) == ["fail_after_acceptance"]


def test_an_empty_listing_while_in_flight_leaves_one_message_and_a_recheck_records_it(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    container: httpx2.Client,
    make_context: Callable[[], EventContext],
    lead_id: str,
) -> None:
    faults.fail_after_acceptance = True
    faults.empty_while_in_flight = True

    intent_id = draft_and_dispatch(store, mailbox, make_context, lead_id)

    assert held_intents(container, lead_id) == [intent_id]
    assert state_of(store, intent_id) == "unknown"
    assert injected(store) == ["fail_after_acceptance", "empty_while_in_flight"]

    reconcile(store, mailbox, make_context, intent_id)

    assert held_intents(container, lead_id) == [intent_id]
    assert state_of(store, intent_id) == "sent"


def test_startup_reconcile_records_a_posted_intent_without_posting_again(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    container: httpx2.Client,
    make_context: Callable[[], EventContext],
    lead_id: str,
) -> None:
    posted = f"i-{uuid.uuid4().hex[:8]}"
    insert_dispatching(store, lead_id, posted, 1)
    mailbox.send(
        lead_id, RECIPIENT, "uw@stand.com", "S", "B",
        {"intent_id": posted, "run_id": "run-1", "kind": "routine_request", "round": 1,
         "payload_hash": payload_hash(RECIPIENT, "S", "B")},
    )  # fmt: skip

    reconcile_dispatching(store, mailbox, make_context)

    assert state_of(store, posted) == "sent"
    assert held_intents(container, lead_id) == [posted]


def test_startup_reconcile_marks_an_unposted_intent_unknown_and_leaves_a_draft(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    container: httpx2.Client,
    make_context: Callable[[], EventContext],
    lead_id: str,
) -> None:
    never_posted = f"i-{uuid.uuid4().hex[:8]}"
    insert_dispatching(store, lead_id, never_posted, 1)
    drafted = create_draft(
        store, make_context(), ASKER, lead_id, "sensitive_request", RECIPIENT, "S2", "B2", []
    )
    store.commit()

    reconcile_dispatching(store, mailbox, make_context)

    assert state_of(store, never_posted) == "unknown"
    assert [(b.kind, b.detail.intent_id) for b in open_blockers(store, lead_id)
            if b.kind == "delivery_unknown"] == [("delivery_unknown", never_posted)]  # fmt: skip
    assert state_of(store, drafted) == "draft"
    assert held_intents(container, lead_id) == []
