# ABOUTME: Tests the underwriter's decisions on the seed-42 leads through the running app: an answer to a failed fire simulation, the decline of lead 000 and its rejection, and a decline of the underwriter's own.
# ABOUTME: The app runs in process with the real steps against Stand's leadgen and mailbox apps in process; the mailbox is read back as the producer's inbox.
import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import first_pass
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.rulings import rulings_in_force
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blockers
from uwh.settings import Settings
from uwh.skills.steps import HELD_FOR_A_CHOICE

LEAD_000, LEAD_003, LEAD_006, LEAD_009 = (
    f"LEAD-00000042-{n}" for n in ("000", "003", "006", "009")
)


@pytest.fixture
def app(settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient) -> Iterator[TestClient]:
    with first_pass(settings, leadgen, mailbox) as client:
        yield client


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


def rule_fire(app: TestClient, lead_id: str, option: str) -> dict[str, Any]:
    return command(
        app,
        "record_ruling",
        lead_id=lead_id,
        choice_id="I13.fire_fail",
        option=option,
        reason="the underwriter decided",
    )


def kinds(db: sqlite3.Connection, lead_id: str) -> list[tuple[str, str | None]]:
    return sorted((b.kind, b.detail.item_kind) for b in open_blockers(db, lead_id))


def notice_item(app: TestClient, lead_id: str) -> tuple[int, str]:
    """The item that reviews the lead's decline notice and the hash an approval echoes."""
    detail = app.get(f"/api/leads/{lead_id}").json()
    (draft,) = [
        d for d in detail["drafts"] if d["kind"] == "decline_notice" and d["state"] == "draft"
    ]
    (item,) = [b for b in detail["blockers"] if b["detail"]["intent_id"] == draft["intent_id"]]
    return item["item_id"], draft["payload_hash"]


def test_the_card_asks_the_choice_in_plain_words(app: TestClient, db: sqlite3.Connection) -> None:
    (card,) = [b for b in open_blockers(db, LEAD_003) if b.kind == "underwriter_question"]

    assert card.detail.text == (
        "The fire simulation failed: decline, or continue under legacy underwriting? "
        "The legacy checklist values are shown."
    )


def held_request(app: TestClient, lead_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The lead's request draft and the item that holds it for the underwriter."""
    detail = app.get(f"/api/leads/{lead_id}").json()
    (draft,) = [
        d
        for d in detail["drafts"]
        if d["kind"] in ("routine_request", "sensitive_request") and d["state"] == "draft"
    ]
    (item,) = [b for b in detail["blockers"] if b["detail"]["intent_id"] == draft["intent_id"]]
    return draft, item


@pytest.mark.parametrize("lead_id", [LEAD_003, LEAD_006])
def test_a_request_waits_for_the_underwriter_while_a_choice_could_decline_the_lead(
    app: TestClient, mailbox: MailboxClient, lead_id: str
) -> None:
    draft, item = held_request(app, lead_id)

    assert item["kind"] == "underwriter_review" and item["detail"]["text"] == HELD_FOR_A_CHOICE
    assert draft["asks"] != []
    assert mailbox.list_for_lead(lead_id) == []


def test_the_underwriter_can_send_the_held_request_before_deciding(
    app: TestClient, db: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    draft, item = held_request(app, LEAD_006)

    sent = command(
        app,
        "approve",
        item_id=item["item_id"],
        artifact_hash=draft["payload_hash"],
        reason="",
    )

    assert sent["accepted"] is True
    assert [m["metadata"]["kind"] for m in mailbox.list_for_lead(LEAD_006)] == ["routine_request"]
    assert kinds(db, LEAD_006) == [("producer_reply", None), ("underwriter_question", None)]


def test_declining_at_the_choice_withdraws_the_held_request(
    app: TestClient, db: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    rule_fire(app, LEAD_006, "decline")

    detail = app.get(f"/api/leads/{LEAD_006}").json()
    assert [d["state"] for d in detail["drafts"] if d["kind"] == "routine_request"] == [
        "closed_unsent"
    ]
    assert kinds(db, LEAD_006) == [("underwriter_review", "draft")]
    assert mailbox.list_for_lead(LEAD_006) == []


def test_answering_legacy_underwriting_replaces_the_card_and_still_holds_the_request(
    app: TestClient, db: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    assert rule_fire(app, LEAD_003, "legacy_underwriting")["accepted"] is True

    (card,) = [b for b in open_blockers(db, LEAD_003) if b.kind == "underwriter_question"]
    assert card.detail.choice_ids == ["I16.distance"]
    plan = app.get(f"/api/leads/{LEAD_003}").json()["plan"]
    assert plan["catalogue_questions"] == ["willing_to_mitigate"]
    # The distance choice could still decline the lead, so the request, now with the question, waits.
    draft, _ = held_request(app, LEAD_003)
    assert "Would the applicant be willing to mitigate greater distance?" in draft["asks"]
    assert mailbox.list_for_lead(LEAD_003) == []
    assert rulings_in_force(db, LEAD_003).choices == {"I13.fire_fail": "legacy_underwriting"}


def test_answering_every_choice_of_a_card_closes_it(
    app: TestClient, db: sqlite3.Connection
) -> None:
    rule_fire(app, LEAD_003, "legacy_underwriting")

    answered = command(
        app,
        "record_ruling",
        lead_id=LEAD_003,
        choice_id="I16.distance",
        option="adequate",
        reason="14 feet is adequate here",
    )

    assert answered["accepted"] is True
    # With no choice left that could decline the lead, only the request remains: its mitigation
    # question makes it a sensitive request, which waits for the underwriter's approval.
    assert kinds(db, LEAD_003) == [("underwriter_review", "draft")]


def test_a_closed_question_card_is_matched_to_its_ruling_through_the_choice_ids_of_the_event_rows(
    app: TestClient,
) -> None:
    rule_fire(app, LEAD_003, "legacy_underwriting")

    rows = app.get(f"/api/leads/{LEAD_003}/events").json()["events"]

    card = next(r for r in rows if r["type"] == "blocker_opened" and r["choice_ids"])
    ruling = next(r for r in rows if r["type"] == "ruling_recorded")
    assert card["item_id"] is not None and card["choice_ids"] == ["I13.fire_fail"]
    assert ruling["choice_ids"] == ["I13.fire_fail"] and ruling["actor"] == "underwriter"
    # The request held for the underwriter's decision is an item of the underwriter's too.
    held = [r for r in rows if r["type"] == "blocker_opened" and HELD_FOR_A_CHOICE in r["summary"]]
    assert held and all(r["item_id"] is not None for r in held)


def test_a_ruling_on_a_choice_that_is_not_open_is_refused(app: TestClient) -> None:
    answer = command(
        app,
        "record_ruling",
        lead_id=LEAD_009,
        choice_id="I13.fire_fail",
        option="decline",
        reason="there is no card",
    )

    assert answer["accepted"] is False and "not an open choice" in answer["reason"]


def test_choosing_to_decline_drafts_the_notice_and_approving_it_sends_it_and_ends_the_lead(
    app: TestClient, db: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    rule_fire(app, LEAD_006, "decline")

    assert kinds(db, LEAD_006) == [("underwriter_review", "draft")]
    item_id, payload_hash = notice_item(app, LEAD_006)
    # The choice gave the decline its reason, so the notice goes without another one.
    approved = command(app, "approve", item_id=item_id, artifact_hash=payload_hash, reason="")

    assert approved["accepted"] is True
    assert db.execute("SELECT reason FROM approvals WHERE intent_id IS NOT NULL").fetchall()[
        -1
    ] == ("the underwriter decided",)
    # The producer was never asked: the decline withdrew the held request.
    assert [m["metadata"]["kind"] for m in mailbox.list_for_lead(LEAD_006)] == ["decline_notice"]
    assert open_blockers(db, LEAD_006) == []
    assert db.execute("SELECT status FROM leads WHERE lead_id = ?", (LEAD_006,)).fetchone() == (
        "declined",
    )


def test_rejecting_the_decline_notice_of_lead_000_suppresses_the_rule_and_sends_the_registry_asks(
    app: TestClient, db: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    item_id, _ = notice_item(app, LEAD_000)

    rejected = command(app, "reject", item_id=item_id, reason="the foundation is acceptable here")

    assert rejected["accepted"] is True
    assert rulings_in_force(db, LEAD_000).suppressed_rules == ["PP-1"]
    assert [m["metadata"]["kind"] for m in mailbox.list_for_lead(LEAD_000)] == ["routine_request"]
    assert kinds(db, LEAD_000) == [("producer_reply", None)]
    plan = app.get(f"/api/leads/{LEAD_000}").json()["plan"]
    assert plan["proposed_decline"] is False
    (overridden,) = [e for e in plan["effects"] if e["effect"]["rule"] == "PP-1"]
    assert overridden["effect"]["type"] == "advisory" and overridden["effect"]["internal"] is True
    (notice,) = db.execute(
        "SELECT state FROM intents WHERE kind = 'decline_notice' AND lead_id = ?", (LEAD_000,)
    ).fetchall()
    assert notice == ("closed_unsent",)


def test_rejecting_a_decline_that_followed_a_choice_reopens_the_choice(
    app: TestClient, db: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    rule_fire(app, LEAD_006, "decline")
    item_id, _ = notice_item(app, LEAD_006)

    command(app, "reject", item_id=item_id, reason="the broker has new information")

    assert rulings_in_force(db, LEAD_006).choices == {}
    # The choice is open again, so the request is drafted again and held for it.
    assert kinds(db, LEAD_006) == [("underwriter_question", None), ("underwriter_review", "draft")]
    assert mailbox.list_for_lead(LEAD_006) == []


def test_rejecting_a_decline_under_legacy_underwriting_reopens_only_the_choice_that_led_to_it(
    app: TestClient, db: sqlite3.Connection
) -> None:
    rule_fire(app, LEAD_003, "legacy_underwriting")
    command(
        app,
        "record_ruling",
        lead_id=LEAD_003,
        choice_id="I16.distance",
        option="too_close",
        reason="14 feet is too close",
    )
    item_id, _ = notice_item(app, LEAD_003)

    command(app, "reject", item_id=item_id, reason="the neighbour is a shed")

    rulings = rulings_in_force(db, LEAD_003)
    assert rulings.choices == {"I13.fire_fail": "legacy_underwriting"}
    assert rulings.suppressed_rules == []
    (card,) = [b for b in open_blockers(db, LEAD_003) if b.kind == "underwriter_question"]
    assert card.detail.choice_ids == ["I16.distance"]


def test_rejecting_a_decline_the_legacy_checklist_reached_suppresses_it_instead_of_reopening_a_loop(
    app: TestClient, db: sqlite3.Connection
) -> None:
    rule_fire(app, LEAD_003, "legacy_underwriting")
    command(
        app,
        "resolve_fact",
        lead_id=LEAD_003,
        key="road_access",
        value="Limited / Dead-end / No Turnaround",
        reason="the map shows a dead end",
    )
    item_id, _ = notice_item(app, LEAD_003)

    command(app, "reject", item_id=item_id, reason="the dead end has a turn-around")

    rulings = rulings_in_force(db, LEAD_003)
    assert rulings.choices == {"I13.fire_fail": "legacy_underwriting"}
    assert rulings.suppressed_rules == ["FS-3"]
    assert app.get(f"/api/leads/{LEAD_003}").json()["plan"]["proposed_decline"] is False


def test_rejecting_the_notice_of_a_decline_the_rules_also_make_withdraws_the_ruling_and_suppresses_the_rule(
    app: TestClient, db: sqlite3.Connection
) -> None:
    command(app, "decline_lead", lead_id=LEAD_000, reason="the applicant is known to us")
    item_id, _ = notice_item(app, LEAD_000)

    command(app, "reject", item_id=item_id, reason="the underwriter thought again")

    rulings = rulings_in_force(db, LEAD_000)
    assert rulings.decline_reason is None
    assert rulings.suppressed_rules == ["PP-1"]
    assert app.get(f"/api/leads/{LEAD_000}").json()["plan"]["proposed_decline"] is False


def test_the_underwriters_own_decline_waits_as_a_notice_and_rejecting_it_withdraws_the_ruling(
    app: TestClient, db: sqlite3.Connection
) -> None:
    declined = command(app, "decline_lead", lead_id=LEAD_009, reason="the applicant is known to us")

    assert declined["accepted"] is True
    assert app.get(f"/api/leads/{LEAD_009}").json()["plan"]["underwriter_decline"] == (
        "the applicant is known to us"
    )
    item_id, _ = notice_item(app, LEAD_009)

    command(app, "reject", item_id=item_id, reason="the underwriter thought again")

    assert rulings_in_force(db, LEAD_009).decline_reason is None
    assert kinds(db, LEAD_009) == [("producer_reply", None)]


def test_discarding_a_held_request_sends_nothing_and_drafts_none_until_the_lead_changes(
    app: TestClient, db: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    _, item = held_request(app, LEAD_006)

    discarded = command(app, "reject", item_id=item["item_id"], reason="declining on the fire risk")

    assert discarded["accepted"] is True
    detail = app.get(f"/api/leads/{LEAD_006}").json()
    assert [d["state"] for d in detail["drafts"] if d["kind"] == "routine_request"] == [
        "closed_unsent"
    ]
    assert kinds(db, LEAD_006) == [("underwriter_question", None)]
    assert mailbox.list_for_lead(LEAD_006) == []
    # A ruling changes the lead, so the request is drafted again and held for the choice now open.
    rule_fire(app, LEAD_006, "legacy_underwriting")
    held_request(app, LEAD_006)


def test_a_request_that_is_the_leads_only_item_cannot_be_discarded(
    app: TestClient, db: sqlite3.Connection
) -> None:
    rule_fire(app, LEAD_003, "legacy_underwriting")
    command(
        app,
        "record_ruling",
        lead_id=LEAD_003,
        choice_id="I16.distance",
        option="adequate",
        reason="14 feet is adequate here",
    )
    _, item = held_request(app, LEAD_003)

    refused = command(app, "reject", item_id=item["item_id"], reason="")

    assert refused["accepted"] is False and "nothing to do" in refused["reason"]
    assert kinds(db, LEAD_003) == [("underwriter_review", "draft")]
