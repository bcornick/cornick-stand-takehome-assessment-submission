# ABOUTME: Tests the limit of two request rounds (10.1) on lead 009: after the second round with the ask still open, a re-evaluation sends no third request and raises the round_limit review, which closes when the underwriter supplies the fact.
# ABOUTME: The second round is made by copying the first sent request into round 2, since a producer's reply is read by a model; the rest is the real first pass, command layer and steps in process.
import json
import sqlite3
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import first_pass
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blockers
from uwh.settings import Settings

LEAD_009 = "LEAD-00000042-009"


@pytest.fixture
def app(settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient) -> Iterator[TestClient]:
    with first_pass(settings, leadgen, mailbox) as client:
        yield client


@pytest.fixture
def db(settings: Settings) -> Iterator[sqlite3.Connection]:
    store = open_store(settings.db_path)
    yield store
    store.close()


def after_two_unanswered_rounds(db: sqlite3.Connection) -> None:
    """Round 1 is answered with nothing that closes the ask; round 2 is sent and answered likewise."""
    db.execute("DELETE FROM blockers WHERE lead_id = ? AND kind = 'producer_reply'", (LEAD_009,))
    db.execute(
        "INSERT INTO intents SELECT ?, run_id, lead_id, 2, kind, recipient, subject, body,"
        " ask_ids_json, payload_hash, state, mailbox_id, lead_revision FROM intents"
        " WHERE lead_id = ?",
        (uuid.uuid4().hex, LEAD_009),
    )
    db.commit()


def reevaluate(app: TestClient, key: str, value: object) -> None:
    answer = app.post(
        "/api/commands",
        json={
            "type": "resolve_fact",
            "payload": {"lead_id": LEAD_009, "key": key, "value": value, "reason": "called"},
        },
    ).json()
    assert answer["accepted"] is True


def test_a_lead_with_asks_open_after_two_rounds_goes_to_the_underwriter_and_gets_no_third_request(
    app: TestClient, db: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    after_two_unanswered_rounds(db)

    reevaluate(app, "occupation", "Teacher")

    (review,) = open_blockers(db, LEAD_009)
    assert (review.kind, review.detail.cause, review.detail.cause_persists) == (
        "underwriter_review",
        "round_limit",
        True,
    )
    assert review.detail.text == "2 requests have been sent and these are still open: Lot Acreage."
    assert db.execute(
        "SELECT COUNT(*) FROM intents WHERE lead_id = ? AND kind = 'routine_request'", (LEAD_009,)
    ).fetchone() == (2,)
    assert len(mailbox.list_for_lead(LEAD_009)) == 1


def test_the_round_limit_review_is_not_opened_twice_and_closes_when_the_fact_is_supplied(
    app: TestClient, db: sqlite3.Connection
) -> None:
    after_two_unanswered_rounds(db)
    reevaluate(app, "occupation", "Teacher")
    reevaluate(app, "occupation", "Nurse")
    assert len(open_blockers(db, LEAD_009)) == 1

    reevaluate(app, "acreage", 0.4)

    assert json.loads(
        db.execute(
            "SELECT ask_ids_json FROM intents WHERE lead_id = ? AND round = 1", (LEAD_009,)
        ).fetchone()[0]
    ) == ["acreage"]
    # The review is gone and the quote packet waits for approval in its place.
    assert [(b.detail.item_kind, b.detail.cause) for b in open_blockers(db, LEAD_009)] == [
        ("draft", None)
    ]


def test_declining_a_lead_at_the_round_limit_closes_the_review_and_the_notice_ends_the_lead(
    app: TestClient, db: sqlite3.Connection
) -> None:
    after_two_unanswered_rounds(db)
    reevaluate(app, "occupation", "Teacher")

    declined = app.post(
        "/api/commands",
        json={
            "type": "decline_lead",
            "payload": {"lead_id": LEAD_009, "reason": "no answer after two requests"},
        },
    ).json()

    assert declined["accepted"] is True
    (notice,) = open_blockers(db, LEAD_009)
    assert (notice.detail.item_kind, notice.detail.text) == (
        "draft",
        "Review this decline notice before it is sent.",
    )
    (payload_hash,) = db.execute(
        "SELECT payload_hash FROM intents WHERE id = ?", (notice.detail.intent_id,)
    ).fetchone()
    approved = app.post(
        "/api/commands",
        json={
            "type": "approve",
            "payload": {"item_id": notice.id, "artifact_hash": payload_hash, "reason": "agreed"},
        },
    ).json()
    assert approved["accepted"] is True
    assert open_blockers(db, LEAD_009) == []
    assert db.execute("SELECT status FROM leads WHERE lead_id = ?", (LEAD_009,)).fetchone() == (
        "declined",
    )
