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


def plan_of(db: sqlite3.Connection, lead_id: str) -> ActionPlan:
    (plan_json,) = db.execute(
        "SELECT plan_json FROM leads WHERE lead_id = ?", (lead_id,)
    ).fetchone()
    return ActionPlan.model_validate_json(plan_json)


def asked(db: sqlite3.Connection, lead_id: str) -> list[str]:
    return [
        ask
        for (ask_ids,) in db.execute(
            "SELECT ask_ids_json FROM intents WHERE lead_id = ?", (lead_id,)
        )
        for ask in json.loads(ask_ids)
    ]


# What each lead of 5's scenario table ends the first pass as: its open blockers (kind and item
# kind) and the kinds of message in the producer's mailbox.
FIRST_PASS = {
    "000": ([("underwriter_review", "draft")], []),
    "001": ([("producer_reply", None)], ["routine_request"]),
    "002": ([("producer_reply", None)], ["routine_request"]),
    "003": ([("underwriter_question", None), ("producer_reply", None)], ["routine_request"]),
    "004": ([("producer_reply", None)], ["routine_request"]),
    "005": ([("producer_reply", None)], ["routine_request"]),
    "006": ([("underwriter_question", None), ("producer_reply", None)], ["routine_request"]),
    "007": ([("producer_reply", None)], ["routine_request"]),
    "008": ([("producer_reply", None)], ["routine_request"]),
    "009": ([("producer_reply", None)], ["routine_request"]),
}


@pytest.mark.parametrize("number", FIRST_PASS)
def test_every_lead_ends_the_first_pass_with_one_wait_or_one_request_and_its_reply_wait(
    first_pass: sqlite3.Connection, mailbox: MailboxClient, number: str
) -> None:
    lead_id = f"LEAD-00000042-{number}"
    waits, mail = FIRST_PASS[number]

    assert sorted(
        (b.kind, b.detail.item_kind) for b in open_blockers(first_pass, lead_id)
    ) == sorted(waits)
    assert [m["metadata"]["kind"] for m in mailbox.list_for_lead(lead_id)] == mail


def test_lead_000_is_a_proposed_decline_with_the_notice_waiting_and_no_request(
    first_pass: sqlite3.Connection,
) -> None:
    plan = plan_of(first_pass, "LEAD-00000042-000")
    (notice,) = first_pass.execute(
        "SELECT kind, state, body FROM intents WHERE lead_id = 'LEAD-00000042-000'"
    ).fetchall()

    (decline,) = [p for p in plan.effects if p.effect.type == "decline"]
    assert plan.proposed_decline and decline.effect.rule == "PP-1"
    assert decline.trace.board_path == ["07:ROOT", "07:LIVING", "07:D1"]
    assert notice[:2] == ("decline_notice", "draft")
    assert "unable to offer coverage" in notice[2]


def test_lead_001_has_the_fire_simulation_undecided_and_no_card(
    first_pass: sqlite3.Connection,
) -> None:
    plan = plan_of(first_pass, "LEAD-00000042-001")

    assert ("fire_simulation", ["p_f"]) in [(u.graph, u.waits_on) for u in plan.undecided]
    assert plan.open_choices == []
    assert "street_address" in asked(first_pass, "LEAD-00000042-001")


@pytest.mark.parametrize(
    ("number", "exclusion"), [("002", "PF-5"), ("005", "PF-1"), ("007", "PF-5")]
)
def test_the_leads_with_a_kyc_score_above_5_carry_the_liability_exclusion(
    first_pass: sqlite3.Connection, number: str, exclusion: str
) -> None:
    plan = plan_of(first_pass, f"LEAD-00000042-{number}")

    assert ("exclusion_or_endorsement", exclusion) in [
        (p.effect.type, p.effect.rule) for p in plan.effects
    ]
    assert not plan.proposed_decline


@pytest.mark.parametrize("number", ["003", "006"])
def test_the_failed_fire_simulation_leads_have_one_card_and_the_siding_requirement_committed(
    first_pass: sqlite3.Connection, mailbox: MailboxClient, number: str
) -> None:
    lead_id = f"LEAD-00000042-{number}"
    plan = plan_of(first_pass, lead_id)
    (card,) = [b for b in open_blockers(first_pass, lead_id) if b.kind == "underwriter_question"]

    assert card.detail.choice_ids == ["I13.fire_fail"]
    assert [c.choice_id for c in plan.open_choices] == ["I13.fire_fail"]
    assert ("requirement", "SD-5") in [
        (p.effect.type, p.effect.rule) for p in plan.effects if p.committed
    ]
    assert plan.catalogue_questions == []  # the mitigation question waits for the choice
    assert "willing_to_mitigate" not in asked(first_pass, lead_id)
    # No protection class question goes out: its lookup is blocked on the address.
    assert not {"fire_dept_response_time", "alternative_water_source"} & set(
        asked(first_pass, lead_id)
    )


def test_lead_003_has_the_occupancy_page_undecided_while_its_conflict_is_open(
    first_pass: sqlite3.Connection,
) -> None:
    lead_id = "LEAD-00000042-003"

    assert ("occupancy", ["months_unoccupied"]) in [
        (u.graph, u.waits_on) for u in plan_of(first_pass, lead_id).undecided
    ]
    assert "months_unoccupied_in_primary_home" in asked(first_pass, lead_id)


def test_lead_006_asks_for_the_roof_material_and_not_the_pool_values_it_holds(
    first_pass: sqlite3.Connection,
) -> None:
    ask_ids = asked(first_pass, "LEAD-00000042-006")

    assert "roof_material" in ask_ids
    assert not {"pool_security", "pool_has_diving_board_or_slide"} & set(ask_ids)


def test_lead_005_asks_the_missing_pool_fields_and_confirms_the_zero_residents(
    first_pass: sqlite3.Connection,
) -> None:
    ask_ids = asked(first_pass, "LEAD-00000042-005")

    assert {"pool_type", "pool_security", "no_residents_in_primary_home"} <= set(ask_ids)
    assert "pool_has_diving_board_or_slide" not in ask_ids


@pytest.mark.parametrize("number", ["004", "005", "006", "009"])
def test_a_lead_with_animals_carries_the_note_that_animals_are_not_evaluated(
    first_pass: sqlite3.Connection, number: str
) -> None:
    plan = plan_of(first_pass, f"LEAD-00000042-{number}")

    assert "animals" in [n.ref for n in plan.not_evaluated]
