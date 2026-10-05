# ABOUTME: Tests the first pass of the running app on the seed-42 queue: lead 008 ends with one sent routine request and an open wait for the producer, and every other lead ends with a request or a stated reason.
# ABOUTME: The app runs in process with the real steps against Stand's leadgen and mailbox apps in process; the mailbox is read back as the producer's inbox.
import json
import sqlite3
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from uwh.api.app import create_app
from uwh.rules.models import ActionPlan
from uwh.runtime.event_types import EventType, PlanBuilt
from uwh.runtime.events import read_events
from uwh.runtime.hashing import hash_json
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blockers
from uwh.settings import Settings

LEAD_008 = "LEAD-00000042-008"


@pytest.fixture
def first_pass(
    settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient
) -> sqlite3.Connection:
    """The database of the app after the first pass of the seed-42 run."""
    seed_42 = replace(settings, seed=42)
    with TestClient(create_app(seed_42, leadgen=leadgen, mailbox=mailbox)) as client:
        assert client.post("/api/run/start?wait=true").status_code == 200
    return open_store(settings.db_path)


def test_lead_008_ends_the_first_pass_with_one_sent_routine_request_for_its_two_asks(
    first_pass: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    (message,) = mailbox.list_for_lead(LEAD_008)

    assert (message["metadata"]["kind"], message["metadata"]["round"]) == ("routine_request", 1)
    assert message["to"] == "broker-desk@producers.example"
    assert message["subject"] == "Information needed for your quote: 8924 Lakeview Blvd"
    # Each ask's wording is in the body once, and no other question is.
    wording = ["When was the property purchased?", "What brand is the electrical panel?"]
    assert [message["body"].count(question) for question in wording] == [1, 1]
    assert message["body"].count("?") == 2
    (intent,) = first_pass.execute(
        "SELECT ask_ids_json, state, kind FROM intents WHERE lead_id = ?", (LEAD_008,)
    ).fetchall()
    assert (json.loads(intent[0]), intent[1], intent[2]) == (
        ["property_purchase_date", "electrical_panel_brand"],
        "sent",
        "routine_request",
    )
    assert first_pass.execute(
        "SELECT status FROM leads WHERE lead_id = ?", (LEAD_008,)
    ).fetchone() == ("in_progress",)
    (blocker,) = open_blockers(first_pass, LEAD_008)
    assert (blocker.kind, blocker.detail.intent_id) == (
        "producer_reply",
        message["metadata"]["intent_id"],
    )


def test_lead_008_has_its_plan_stored_with_the_two_pages_not_evaluated(
    first_pass: sqlite3.Connection,
) -> None:
    plan_json, plan_hash = first_pass.execute(
        "SELECT plan_json, plan_hash FROM leads WHERE lead_id = ?", (LEAD_008,)
    ).fetchone()
    plan = ActionPlan.model_validate_json(plan_json)

    assert plan_hash == hash_json(plan.model_dump(mode="json"))
    assert sorted(p.effect.rule for p in plan.effects) == ["RC-2", "RF-1", "SD-1"]
    assert [n.ref for n in plan.not_evaluated] == ["electrical", "plumbing"]
    (built,) = [
        e for e in read_events(first_pass, lead_id=LEAD_008) if e.type == EventType.plan_built
    ]
    assert built.payload == PlanBuilt(plan=plan.model_dump(mode="json"), plan_hash=plan_hash)


def test_every_lead_ends_the_first_pass_with_one_request_sent_and_the_wait_for_its_reply(
    first_pass: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    for (lead_id,) in first_pass.execute("SELECT lead_id FROM leads ORDER BY rowid").fetchall():
        (blocker,) = open_blockers(first_pass, lead_id)
        assert blocker.kind == "producer_reply", lead_id
        assert len(mailbox.list_for_lead(lead_id)) == 1, lead_id
