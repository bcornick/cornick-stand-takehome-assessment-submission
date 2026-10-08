# ABOUTME: Tests the first pass of the running app on the seed-42 queue: lead 008 ends with one sent routine request and an open wait for the producer, and the plan and the asks of the other leads that differ.
# ABOUTME: The app runs in process with the real steps against Stand's leadgen and mailbox apps in process; the mailbox is read back as the producer's inbox.
import json
import sqlite3
from collections.abc import Iterator

import pytest

from tests.api.helpers import REGISTRY, restore_first_pass
from uwh.api.leads import lead_detail
from uwh.rules.models import ActionPlan, Resolution
from uwh.rules.registry import load_registry
from uwh.runtime.event_types import EventType, PlanBuilt, TriageCompleted
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
) -> Iterator[sqlite3.Connection]:
    """The database of the app after the first pass of the seed-42 run."""
    restore_first_pass(settings, leadgen, mailbox)
    db = open_store(settings.db_path)
    yield db
    db.close()


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


def test_lead_008s_detail_groups_its_plan_by_page(first_pass: sqlite3.Connection) -> None:
    detail = lead_detail(first_pass, LEAD_008, load_registry(str(REGISTRY)))

    assert detail is not None
    by_page = {page.key: page for page in detail.pages}
    assert sorted(p.effect.rule for page in detail.pages for p in page.effects) == [
        "RC-2",
        "RF-1",
        "SD-1",
    ]
    assert [n.ref for n in by_page["electrical"].not_evaluated] == ["electrical"]
    assert by_page["electrical"].effects == [] and "plumbing" in by_page
    assert len(by_page) == 5


def test_the_request_to_a_web_applicant_speaks_to_them_and_one_to_a_broker_does_not(
    first_pass: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    (web,) = mailbox.list_for_lead("LEAD-00000042-003")
    (broker,) = mailbox.list_for_lead("LEAD-00000042-006")

    assert "What is your date of birth?" in web["body"]
    assert "applicant" not in web["body"]
    assert "What is the applicant's last name?" in broker["body"]


def test_the_latest_triage_of_a_lead_is_the_one_taken_after_its_lookups(
    first_pass: sqlite3.Connection,
) -> None:
    triages = [
        e.payload.fields
        for e in read_events(first_pass, lead_id=LEAD_008)
        if e.type == EventType.triage_completed and isinstance(e.payload, TriageCompleted)
    ]

    assert [t["replacement_cost"]["resolution"] for t in triages] == ["fetch", "none"]


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


def test_lead_003s_detail_lists_the_field_it_asked_for_as_missing_and_sections_every_field(
    first_pass: sqlite3.Connection,
) -> None:
    detail = lead_detail(first_pass, "LEAD-00000042-003", load_registry(str(REGISTRY)))

    assert detail is not None
    sections = {field.key: field.section for field in detail.fields}
    missing = {field.key: field.resolution for field in detail.missing_fields}
    assert missing["insured_dob"] == Resolution.ask
    assert Resolution.fetch in missing.values()
    assert not set(missing) & {fact.key for fact in detail.facts}
    assert sections["insured_dob"] == "Insured"
    assert sections["q:contact_email"] == "Contact"
    assert all(sections[key] for key in missing)


def test_a_lead_with_no_address_is_named_without_the_runs_seed(
    first_pass: sqlite3.Connection,
) -> None:
    detail = lead_detail(first_pass, "LEAD-00000042-000", load_registry(str(REGISTRY)))

    assert detail is not None
    assert detail.label == "LEAD-000"
    (notice,) = [draft for draft in detail.drafts if draft.kind == "decline_notice"]
    assert notice.subject == "Regarding your submission: LEAD-000"
    assert detail.decline_reason is not None
    assert detail.decline_reason.endswith("so the post and pier page declines it (PP-1)")
    assert not any("00000042" in draft.subject + draft.body for draft in detail.drafts)
