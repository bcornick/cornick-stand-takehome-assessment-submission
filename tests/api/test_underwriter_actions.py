# ABOUTME: Tests each action the detail pane offers, through the app's routes: approve, edit and reject a draft, approve and reject a pending observation, a ruling, a resolved fact, a decline with its notice, and a pasted reply.
# ABOUTME: The app runs in process with the real steps against Stand's leadgen and mailbox apps in process; each test asserts the effect read back from the lead detail and the mailbox, never the command's answer alone.
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import FIXTURE_REPLIES, first_pass
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.rulings import rulings_in_force
from uwh.runtime.store import open_store
from uwh.settings import Settings


def lead_id(number: str) -> str:
    return f"LEAD-00000042-{number}"


@pytest.fixture
def app(settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient) -> Iterator[TestClient]:
    with first_pass(settings, leadgen, mailbox) as client:
        yield client


@pytest.fixture
def answered(app: TestClient) -> TestClient:
    """The app after the fixture replies have been delivered."""
    assert app.post("/api/replies/fixtures").status_code == 200
    return app


@pytest.fixture
def db(settings: Settings) -> Iterator[sqlite3.Connection]:
    store = open_store(settings.db_path)
    yield store
    store.close()


def command(app: TestClient, command_type: str, **payload: Any) -> dict[str, Any]:
    response = app.post("/api/commands", json={"type": command_type, "payload": payload})
    assert response.status_code == 200
    answer: dict[str, Any] = response.json()
    return answer


def detail(app: TestClient, number: str) -> dict[str, Any]:
    answer: dict[str, Any] = app.get(f"/api/leads/{lead_id(number)}").json()
    return answer


def item_of(lead: dict[str, Any], item_kind: str) -> dict[str, Any]:
    (item,) = [b for b in lead["blockers"] if b["detail"]["item_kind"] == item_kind]
    return item


def draft_of(lead: dict[str, Any], kind: str) -> dict[str, Any]:
    (draft,) = [d for d in lead["drafts"] if d["kind"] == kind]
    return draft


def sent_kinds(mailbox: MailboxClient, number: str) -> list[str]:
    return sorted(m["metadata"]["kind"] for m in mailbox.list_for_lead(lead_id(number)))


def approve_packet(app: TestClient, number: str, hash_: str | None = None) -> dict[str, Any]:
    lead = detail(app, number)
    return command(
        app,
        "approve",
        item_id=item_of(lead, "draft")["item_id"],
        artifact_hash=hash_ or draft_of(lead, "quote_packet")["payload_hash"],
        reason="the packet matches the plan",
    )


def test_approving_a_waiting_packet_sends_it_and_ends_the_lead_at_a_quote(
    answered: TestClient, mailbox: MailboxClient
) -> None:
    assert approve_packet(answered, "008")["accepted"] is True

    lead = detail(answered, "008")
    assert (lead["status"], lead["blockers"]) == ("quote_sent", [])
    assert sent_kinds(mailbox, "008") == ["quote_packet", "routine_request"]


def test_an_edited_packet_waits_again_and_only_its_new_hash_approves_it(
    answered: TestClient, mailbox: MailboxClient
) -> None:
    before = draft_of(detail(answered, "009"), "quote_packet")

    edited = command(
        answered,
        "edit_draft",
        intent_id=before["intent_id"],
        subject="Your quote, checked",
        body="Checked by the underwriter.",
        reason="the opening was too stiff",
    )

    assert edited["accepted"] is True
    after = draft_of(detail(answered, "009"), "quote_packet")
    assert (after["subject"], after["body"], after["state"]) == (
        "Your quote, checked",
        "Checked by the underwriter.",
        "draft",
    )
    assert after["payload_hash"] != before["payload_hash"]
    stale = approve_packet(answered, "009", before["payload_hash"])
    assert stale["accepted"] is False and stale["reason"]
    assert sent_kinds(mailbox, "009") == ["routine_request"]
    assert approve_packet(answered, "009")["accepted"] is True
    (packet,) = [
        m for m in mailbox.list_for_lead(lead_id("009")) if m["metadata"]["kind"] == "quote_packet"
    ]
    assert packet["subject"] == "Your quote, checked"


def test_rejecting_a_packet_records_the_reason_and_sends_nothing(
    answered: TestClient, db: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    lead = detail(answered, "004")

    rejected = command(
        answered, "reject", item_id=item_of(lead, "draft")["item_id"], reason="the roof is wrong"
    )

    assert rejected["accepted"] is True
    assert db.execute(
        "SELECT decision, reason FROM approvals WHERE lead_id = ?", (lead_id("004"),)
    ).fetchall() == [("rejected", "the roof is wrong")]
    assert draft_of(detail(answered, "004"), "quote_packet")["state"] == "draft"
    assert sent_kinds(mailbox, "004") == ["routine_request"]


@pytest.mark.parametrize(
    ("decision", "effective_value"), [("approve", 5), ("reject", 3)], ids=["approve", "reject"]
)
def test_a_pending_value_becomes_the_fact_when_approved_and_stays_out_when_rejected(
    answered: TestClient, decision: str, effective_value: int
) -> None:
    item = item_of(detail(answered, "003"), "observation")
    assert item["observation"]["value"] == 5

    answer = command(answered, decision, item_id=item["item_id"], reason="the reply is clear")

    assert answer["accepted"] is True
    lead = detail(answered, "003")
    assert [b for b in lead["blockers"] if b["detail"]["item_kind"] == "observation"] == []
    (fact,) = [f for f in lead["facts"] if f["key"] == "months_unoccupied"]
    assert fact["value"] == effective_value


def test_a_ruling_with_a_reason_closes_the_card_and_without_one_is_not_accepted(
    app: TestClient, db: sqlite3.Connection
) -> None:
    ruling = {
        "lead_id": lead_id("003"),
        "choice_id": "I13.fire_fail",
        "option": "legacy_underwriting",
    }
    blank = app.post(
        "/api/commands", json={"type": "record_ruling", "payload": {**ruling, "reason": ""}}
    )
    assert blank.status_code == 422
    assert rulings_in_force(db, lead_id("003")).choices == {}

    accepted = command(app, "record_ruling", **ruling, reason="the checklist is satisfied")

    assert accepted["accepted"] is True
    assert rulings_in_force(db, lead_id("003")).choices == {"I13.fire_fail": "legacy_underwriting"}


def test_a_resolved_fact_is_the_effective_value_with_the_underwriter_as_its_source(
    app: TestClient,
) -> None:
    answer = command(
        app,
        "resolve_fact",
        lead_id=lead_id("002"),
        key="coverage_a",
        value=500000,
        reason="the producer said so by phone",
    )

    assert answer["accepted"] is True
    (fact,) = [f for f in detail(app, "002")["facts"] if f["key"] == "coverage_a"]
    assert (fact["value"], fact["source"]) == (500000, "underwriter")


def test_declining_a_lead_drafts_its_notice_and_approving_the_notice_ends_the_lead(
    app: TestClient, mailbox: MailboxClient
) -> None:
    answer = command(app, "decline_lead", lead_id=lead_id("005"), reason="outside our appetite")

    assert answer["accepted"] is True
    waiting = detail(app, "005")
    assert waiting["plan"]["underwriter_decline"] == "outside our appetite"
    notice = draft_of(waiting, "decline_notice")
    assert (notice["state"], sent_kinds(mailbox, "005")) == ("draft", ["routine_request"])

    approved = command(
        app,
        "approve",
        item_id=item_of(waiting, "draft")["item_id"],
        artifact_hash=notice["payload_hash"],
        reason="the notice is accurate",
    )

    assert approved["accepted"] is True
    assert detail(app, "005")["status"] == "declined"
    assert sent_kinds(mailbox, "005") == ["decline_notice", "routine_request"]


def test_a_pasted_reply_to_the_sent_request_is_read_and_its_values_become_facts(
    app: TestClient,
) -> None:
    waiting = detail(app, "007")
    request = [d for d in waiting["drafts"] if d["state"] == "sent"][-1]
    body = Path(FIXTURE_REPLIES / f"{lead_id('007')}.txt").read_text(encoding="utf-8")

    answer = app.post(
        "/api/replies",
        json={"lead_id": lead_id("007"), "intent_id": request["intent_id"], "body": body},
    ).json()

    assert answer["accepted"] is True
    facts = {f["key"]: f for f in detail(app, "007")["facts"]}
    assert (facts["zip"]["value"], facts["zip"]["source"]) == ("34102", "reply")
    repeated = app.post(
        "/api/replies",
        json={"lead_id": lead_id("007"), "intent_id": request["intent_id"], "body": body},
    ).json()
    assert repeated["accepted"] is False and repeated["reason"]
