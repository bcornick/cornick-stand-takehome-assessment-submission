# ABOUTME: Tests the Post & Pier acceptance case of 9.6 through the app: a deck height a reply supplies makes the plan a proposed decline, and no quote packet is built.
# ABOUTME: Lead 000's decline is rejected so its registry asks go out, and its reading is a hand-made recording in a temporary directory, since no committed recording answers a deck height.
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import first_pass, record_reading
from uwh.rules.models import ActionPlan
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.store import open_store
from uwh.settings import Settings

LEAD_000 = "LEAD-00000042-000"


@pytest.fixture
def app(
    settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient, tmp_path: Path
) -> Iterator[TestClient]:
    with first_pass(replace(settings, recordings_dir=str(tmp_path)), leadgen, mailbox) as client:
        yield client


@pytest.fixture
def db(settings: Settings) -> Iterator[sqlite3.Connection]:
    store = open_store(settings.db_path)
    yield store
    store.close()


def command(app: TestClient, command_type: str, **payload: Any) -> None:
    response = app.post("/api/commands", json={"type": command_type, "payload": payload})
    assert response.json()["accepted"] is True, response.json()


def test_a_deck_height_a_reply_supplies_declines_and_no_packet_is_built(
    app: TestClient, db: sqlite3.Connection, tmp_path: Path
) -> None:
    detail = app.get(f"/api/leads/{LEAD_000}").json()
    (notice,) = [b for b in detail["blockers"] if b["detail"]["item_kind"] == "draft"]
    command(app, "reject", item_id=notice["item_id"], reason="the foundation is acceptable here")
    command(
        app,
        "resolve_fact",
        lead_id=LEAD_000,
        key="post_pier_supports_living_area",
        value=False,
        reason="the broker confirmed the pier carries a deck only",
    )
    (intent_id,) = db.execute(
        "SELECT id FROM intents WHERE lead_id = ? AND kind = 'routine_request'", (LEAD_000,)
    ).fetchone()
    body = "The home was built in 2005 and the deck is 15 feet above grade."
    record_reading(
        db,
        tmp_path,
        LEAD_000,
        intent_id,
        body,
        [
            {"ask_id": "year_built", "field": "year_built", "value": 2005, "quote": "2005"},
            {
                "ask_id": "deck_height_ft",
                "field": "deck_height_ft",
                "value": 15,
                "quote": "15 feet",
            },
        ],
    )

    reply = app.post(
        "/api/replies", json={"lead_id": LEAD_000, "intent_id": intent_id, "body": body}
    ).json()

    assert reply["accepted"] is True, reply
    (plan_json,) = db.execute(
        "SELECT plan_json FROM leads WHERE lead_id = ?", (LEAD_000,)
    ).fetchone()
    plan = ActionPlan.model_validate_json(plan_json)
    assert plan.proposed_decline
    assert [p.effect.rule for p in plan.effects if p.effect.type == "decline"] == ["PP-5"]
    kinds = db.execute(
        "SELECT kind FROM intents WHERE lead_id = ? AND state = 'draft'", (LEAD_000,)
    ).fetchall()
    assert kinds == [("decline_notice",)]
    assert db.execute(
        "SELECT COUNT(*) FROM intents WHERE lead_id = ? AND kind = 'quote_packet'", (LEAD_000,)
    ).fetchone() == (0,)
