# ABOUTME: Tests GET /api/leads and GET /api/leads/{id} (A.5, section 11): the queue's order, group and next action over a constructed set of leads, and lead 008's detail through the app from the waiting request to the approved quote packet.
# ABOUTME: The queue is built from stored state; the lead 008 test runs the app in process against Stand's leadgen and mailbox apps and reads the packet's id and hash from the detail, as the page does.
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import LEAD_008, first_pass
from uwh.api.leads import lead_events, queue_rows
from uwh.runtime.event_types import (
    BlockerDetail,
    BlockerKind,
    BlockerOwner,
    EventType,
    FactObserved,
    MessageSent,
    ReplyReceived,
)
from uwh.runtime.events import EventContext, append_event
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.store import open_store
from uwh.runtime.waits import close_blocker, open_blocker
from uwh.settings import Settings

# Tuesday 07:00, a business day after every lead below was received.
NOW = datetime(2026, 6, 30, 7, 0, tzinfo=UTC)
CONTEXT = EventContext("run-1", "replay", "workflow", "r" * 64, NOW, NOW)


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    return open_store(str(tmp_path / "app.db"))


def add_lead(
    db: sqlite3.Connection,
    lead_id: str,
    status: str,
    effective_date: str | None,
    *blockers: tuple[BlockerKind, BlockerOwner],
    asks: str = "[]",
) -> None:
    db.execute(
        "INSERT INTO leads (lead_id, run_id, source, received_at, status, revision)"
        " VALUES (?, 'run-1', 'web', '2026-06-29T07:00:00Z', ?, 0)",
        (lead_id, status),
    )
    if effective_date is not None:
        cursor = db.execute(
            "INSERT INTO observations (lead_id, key, value_json, source, evidence_json, status)"
            " VALUES (?, 'effective_date', ?, 'submitted', '{}', 'accepted')",
            (lead_id, f'"{effective_date}"'),
        )
        db.execute(
            "INSERT INTO effective_facts (lead_id, key, observation_id, confirmed)"
            " VALUES (?, 'effective_date', ?, 0)",
            (lead_id, cursor.lastrowid),
        )
    for kind, owner in blockers:
        item_kind = "no_contact_route" if kind == "underwriter_review" else None
        detail = BlockerDetail(item_kind=item_kind, resume_trigger="resumes", text="waiting")
        open_blocker(db, CONTEXT, lead_id, kind, owner, detail)
    db.execute(
        "INSERT INTO intents (id, lead_id, round, kind, ask_ids_json, state)"
        " VALUES (?, ?, 1, 'routine_request', ?, 'sent')",
        (f"I-{lead_id}", lead_id, asks),
    )
    db.commit()


def test_the_queue_lists_the_underwriter_first_then_data_and_producer_then_finished(
    db: sqlite3.Connection,
) -> None:
    review = ("underwriter_review", "underwriter")
    producer = ("producer_reply", "producer")
    add_lead(db, "L-finished", "quote_sent", "2026-06-01")
    add_lead(db, "L-no-date", "in_progress", None, producer)
    add_lead(db, "L-data", "in_progress", "2026-07-02", ("data", "data_team"))
    add_lead(db, "L-producer", "in_progress", "2026-07-01", producer, asks='["a", "b"]')
    add_lead(db, "L-late-review", "in_progress", "2026-07-20", producer, review)
    add_lead(db, "L-early-review", "in_progress", "2026-07-10", review)

    rows = queue_rows(db, NOW)

    assert [
        (r.lead_id, r.group, r.primary_next_action, r.waits_on, r.effective_date, r.ask_count)
        for r in rows
    ] == [
        (
            "L-early-review",
            "blocked_on_underwriter",
            "underwriter_review",
            "underwriter",
            "2026-07-10",
            0,
        ),
        (
            "L-late-review",
            "blocked_on_underwriter",
            "underwriter_review",
            "underwriter",
            "2026-07-20",
            0,
        ),
        (
            "L-producer",
            "waiting_on_data_or_producer",
            "producer_reply",
            "producer",
            "2026-07-01",
            2,
        ),
        ("L-data", "waiting_on_data_or_producer", "data", "data_team", "2026-07-02", 0),
        ("L-no-date", "waiting_on_data_or_producer", "producer_reply", "producer", None, 0),
        ("L-finished", "finished", None, None, "2026-06-01", 0),
    ]
    assert {r.age_business_days for r in rows} == {1.0}


def test_lead_008_shows_its_waiting_request_then_the_packet_that_the_underwriter_approves(
    settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient
) -> None:
    with first_pass(settings, leadgen, mailbox) as app:
        (row,) = [r for r in app.get("/api/leads").json() if r["lead_id"] == LEAD_008]
        assert row["group"] == "waiting_on_data_or_producer"
        assert (row["primary_next_action"], row["waits_on"], row["ask_count"]) == (
            "producer_reply",
            "producer",
            2,
        )
        waiting = app.get(f"/api/leads/{LEAD_008}").json()
        assert [b["kind"] for b in waiting["blockers"]] == ["producer_reply"]
        assert [(d["kind"], d["state"]) for d in waiting["drafts"]] == [("routine_request", "sent")]
        assert {f["key"]: f["source"] for f in waiting["facts"]}["street_address"] == "submitted"
        assert waiting["plan"]["not_evaluated"][0]["text"].endswith("is not evaluated.")
        fields = {f["key"]: f for f in waiting["fields"]}
        assert fields["coverage_a"]["kind"] == "integer" and fields["coverage_a"]["label"]
        assert "q:contact_email" in fields

        assert app.post("/api/replies/fixtures").status_code == 200
        reviewing = app.get(f"/api/leads/{LEAD_008}").json()
        (item,) = reviewing["blockers"]
        (packet,) = [d for d in reviewing["drafts"] if d["kind"] == "quote_packet"]
        assert item["detail"]["item_kind"] == "draft"
        assert (item["detail"]["intent_id"], packet["state"]) == (packet["intent_id"], "draft")

        stale = app.post(
            "/api/commands",
            json={
                "type": "approve",
                "payload": {"item_id": item["item_id"], "artifact_hash": "0" * 64, "reason": "ok"},
            },
        ).json()
        assert stale["accepted"] is False
        assert [m["metadata"]["kind"] for m in mailbox.list_for_lead(LEAD_008)] == [
            "routine_request"
        ]

        approved = app.post(
            "/api/commands",
            json={
                "type": "approve",
                "payload": {
                    "item_id": item["item_id"],
                    "artifact_hash": packet["payload_hash"],
                    "reason": "the packet matches the plan",
                },
            },
        ).json()

        assert approved["accepted"] is True
        (row,) = [r for r in app.get("/api/leads").json() if r["lead_id"] == LEAD_008]
        assert (row["status"], row["group"], row["primary_next_action"]) == (
            "quote_sent",
            "finished",
            None,
        )
        sent = app.get(f"/api/leads/{LEAD_008}").json()
        assert [d["state"] for d in sent["drafts"]] == ["sent", "sent"]
        assert sent["blockers"] == []
        packets = [
            m for m in mailbox.list_for_lead(LEAD_008) if m["metadata"]["kind"] == "quote_packet"
        ]
        assert [m["metadata"]["payload_hash"] for m in packets] == [packet["payload_hash"]]


def test_an_unknown_lead_is_not_found(client: TestClient) -> None:
    assert client.get("/api/leads/LEAD-missing").status_code == 404


def test_the_items_are_the_open_reviews_and_questions_of_every_lead_and_no_producer_wait(
    settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient
) -> None:
    with first_pass(settings, leadgen, mailbox) as app:
        items = app.get("/api/items").json()

        assert [(i["lead_id"][-3:], i["kind"], i["detail"]["item_kind"]) for i in items] == [
            ("000", "underwriter_review", "draft"),
            ("003", "underwriter_question", None),
            ("006", "underwriter_question", None),
        ]
        for item in items:
            blockers = app.get(f"/api/leads/{item['lead_id']}").json()["blockers"]
            assert item["item_id"] in [b["item_id"] for b in blockers]
        assert items[1]["detail"]["choice_ids"] == ["I13.fire_fail"]
        assert items[0]["detail"]["text"] != ""


def test_before_a_run_there_are_no_items(client: TestClient) -> None:
    assert client.get("/api/items").json() == []


def test_the_events_of_a_lead_come_in_id_order_with_a_summary_each(
    settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient
) -> None:
    with first_pass(settings, leadgen, mailbox) as app:
        body = app.get(f"/api/leads/{LEAD_008}/events").json()

        events = body["events"]
        ids = [e["id"] for e in events]
        assert body["lead_id"] == LEAD_008
        assert ids == sorted(ids) and len(set(ids)) == len(ids)
        (sent,) = [e for e in events if e["type"] == "message_sent"]
        assert sent["summary"] == "Sent the message to the producer"
        assert {e["actor"] for e in events} >= {"workflow"}
        assert {e["mode"] for e in events} == {"replay"}


def test_an_event_row_carries_what_the_conversation_shows_of_it(db: sqlite3.Connection) -> None:
    add_lead(
        db, "L-1", "in_progress", None, ("underwriter_review", "underwriter"), ("data", "data_team")
    )
    blocker_id, data_wait_id = (id for (id,) in db.execute("SELECT id FROM blockers ORDER BY id"))
    db.execute("UPDATE intents SET subject = 'Need details', body = 'Please send them.'")
    append_event(
        db,
        CONTEXT,
        EventType.message_sent,
        MessageSent(intent_id="I-L-1", mailbox_id=1),
        lead_id="L-1",
    )
    append_event(
        db,
        CONTEXT,
        EventType.reply_received,
        ReplyReceived(intent_id="I-L-1", body="Here they are.", body_hash="h"),
        lead_id="L-1",
    )
    append_event(
        db,
        CONTEXT,
        EventType.fact_observed,
        FactObserved(
            observation_id=1,
            key="effective_date",
            value="2026-07-01",
            source="submitted",
            evidence={},
            status="accepted",
        ),
        lead_id="L-1",
    )
    close_blocker(db, CONTEXT, blocker_id)
    close_blocker(db, CONTEXT, data_wait_id)
    db.commit()

    lead = lead_events(db, "L-1")

    assert lead is not None
    # The underwriter's review is an item when it opens and closes; the wait on data is none.
    assert [
        row.item_id
        for row in lead.events
        if row.type in (EventType.blocker_opened, EventType.blocker_closed)
    ] == [blocker_id, None, blocker_id, None]
    rows = {row.type: row for row in lead.events}
    sent = rows[EventType.message_sent].message
    assert sent is not None and (sent.subject, sent.body) == ("Need details", "Please send them.")
    reply = rows[EventType.reply_received].message
    assert reply is not None and (reply.subject, reply.body) == (None, "Here they are.")
    assert rows[EventType.fact_observed].fact_key == "effective_date"
    assert rows[EventType.fact_observed].message is None
    assert rows[EventType.message_sent].item_id is None


def test_the_events_of_an_unknown_lead_are_not_found(client: TestClient) -> None:
    assert client.get("/api/leads/LEAD-missing/events").status_code == 404
