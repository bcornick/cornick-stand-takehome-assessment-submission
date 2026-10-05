# ABOUTME: Tests GET /api/leads and GET /api/leads/{id} (A.5, section 11): the queue's order, group and next action over a constructed set of leads, and lead 008's detail through the app from the waiting request to the approved quote packet.
# ABOUTME: The queue is built from stored state; the lead 008 test runs the app in process against Stand's leadgen and mailbox apps and reads the packet's id and hash from the detail, as the page does.
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import LEAD_008, first_pass
from uwh.api.leads import queue_rows
from uwh.runtime.event_types import BlockerDetail, BlockerKind, BlockerOwner
from uwh.runtime.events import EventContext
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blocker
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

        assert app.post("/api/replies/fixtures").status_code == 200
        reviewing = app.get(f"/api/leads/{LEAD_008}").json()
        (item,) = reviewing["blockers"]
        (packet,) = [d for d in reviewing["drafts"] if d["kind"] == "quote_packet"]
        assert item["detail"]["item_kind"] == "draft"
        assert (item["detail"]["intent_id"], packet["state"]) == (packet["intent_id"], "draft")

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


def test_an_unknown_lead_is_not_found(client: TestClient) -> None:
    assert client.get("/api/leads/LEAD-missing").status_code == 404
