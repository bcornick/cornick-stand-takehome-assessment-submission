# ABOUTME: Tests the FaultPlan hook on the mailbox client (13.1): a send the mailbox accepted whose result is lost, a listing that is empty while a request is in flight, and a hold that lets a test act while a post is in flight.
# ABOUTME: Each fault is read back from Stand's mailbox in process and, through the send primitive, from the event log: it is recorded as `fault_injected` and leaves exactly one message per intent.
import sqlite3
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from tests.runtime.conftest import ASKER
from tests.runtime.conftest import LEAD_ID as LEAD

from uwh.runtime.event_types import EventType, FaultInjected
from uwh.runtime.events import EventContext, read_events
from uwh.runtime.faults import FaultPlan
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.send import create_draft, dispatch


def send_one(client: MailboxClient, intent: str = "i-1") -> dict[str, Any]:
    return client.send(
        LEAD, "p@example.com", "uw@stand.com", "Subject", "Body", {"intent_id": intent}
    )


def listed_intents(client: MailboxClient) -> list[str]:
    listed = sorted(
        client.list_for_lead(LEAD), key=lambda m: m["id"]
    )  # the mailbox lists newest first
    return [m["metadata"]["intent_id"] for m in listed]


def injected(db: sqlite3.Connection) -> list[str]:
    return [
        e.payload.fault
        for e in read_events(db)
        if e.type == EventType.fault_injected and isinstance(e.payload, FaultInjected)
    ]


def test_fail_after_acceptance_loses_the_result_of_one_send_the_mailbox_accepted(
    mailbox: MailboxClient, faults: FaultPlan
) -> None:
    faults.fail_after_acceptance = True

    with pytest.raises(httpx2.HTTPError):
        send_one(mailbox)
    send_one(mailbox, "i-2")

    assert listed_intents(mailbox) == ["i-1", "i-2"]
    assert faults.take_injected() == ["fail_after_acceptance"]
    assert faults.take_injected() == []


def test_a_listing_is_empty_while_a_request_is_in_flight(
    mailbox: MailboxClient, faults: FaultPlan
) -> None:
    seen: list[list[str]] = []
    faults.empty_while_in_flight = True
    faults.hold_in_flight = lambda: seen.append(listed_intents(mailbox))

    send_one(mailbox)

    assert seen == [[]]
    assert listed_intents(mailbox) == ["i-1"]
    assert faults.take_injected() == ["empty_while_in_flight"]


def test_a_listing_while_a_request_is_in_flight_shows_the_message_when_the_fault_is_not_armed(
    mailbox: MailboxClient, faults: FaultPlan
) -> None:
    seen: list[list[str]] = []
    faults.hold_in_flight = lambda: seen.append(listed_intents(mailbox))

    send_one(mailbox)

    assert seen == [["i-1"]]
    assert faults.take_injected() == []


def test_a_listing_after_a_post_has_returned_shows_the_message_though_the_fault_is_armed(
    mailbox: MailboxClient, faults: FaultPlan
) -> None:
    faults.empty_while_in_flight = True
    send_one(mailbox)

    assert listed_intents(mailbox) == ["i-1"]
    assert faults.take_injected() == []


def test_a_lost_result_leaves_the_request_in_flight_for_the_next_listing_only(
    mailbox: MailboxClient, faults: FaultPlan
) -> None:
    faults.fail_after_acceptance = True
    faults.empty_while_in_flight = True
    with pytest.raises(httpx2.HTTPError):
        send_one(mailbox)

    assert listed_intents(mailbox) == []
    assert listed_intents(mailbox) == ["i-1"]
    assert faults.take_injected() == ["fail_after_acceptance", "empty_while_in_flight"]


def test_a_client_with_no_plan_injects_nothing(stand_mailbox_client: httpx2.Client) -> None:
    client = MailboxClient(stand_mailbox_client)
    client.reset()

    send_one(client)

    assert listed_intents(client) == ["i-1"]


def draft_and_dispatch(
    store: sqlite3.Connection, mailbox: MailboxClient, make_context: Callable[[], EventContext]
) -> str:
    intent_id = create_draft(
        store,
        make_context(),
        ASKER,
        LEAD,
        "routine_request",
        "p@example.com",
        "Subject",
        "Body",
        [],
    )
    store.commit()
    dispatch(store, mailbox, make_context, intent_id)
    return intent_id


def test_a_lost_result_is_reconciled_to_sent_with_one_message_and_a_fault_event(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Callable[[], EventContext],
) -> None:
    faults.fail_after_acceptance = True

    intent_id = draft_and_dispatch(store, mailbox, make_context)

    assert listed_intents(mailbox) == [intent_id]
    assert injected(store) == ["fail_after_acceptance"]
    (state,) = store.execute("SELECT state FROM intents WHERE id = ?", (intent_id,)).fetchone()
    assert state == "sent"


def test_a_lost_result_and_an_empty_listing_leave_one_message_and_an_unknown_intent(
    store: sqlite3.Connection,
    mailbox: MailboxClient,
    faults: FaultPlan,
    make_context: Callable[[], EventContext],
) -> None:
    faults.fail_after_acceptance = True
    faults.empty_while_in_flight = True

    intent_id = draft_and_dispatch(store, mailbox, make_context)

    assert listed_intents(mailbox) == [intent_id]
    assert injected(store) == ["fail_after_acceptance", "empty_while_in_flight"]
    (state,) = store.execute("SELECT state FROM intents WHERE id = ?", (intent_id,)).fetchone()
    assert state == "unknown"
    dispatch(store, mailbox, make_context, intent_id)
    assert listed_intents(mailbox) == [intent_id]
